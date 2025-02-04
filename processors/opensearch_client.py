import json

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

from config.settings import (
    AWS_REGION,
    BEDROCK_LLM_MODEL,
    OPENSEARCH_ENDPOINT,
    OPENSEARCH_INDEX,
    OPENSEARCH_EMBEDDING_DIM,
)
from processors.bedrock_embedder import BedrockEmbedder
from processors.neptune_client import NeptuneGraph


def get_aws_auth():
    credentials = boto3.Session().get_credentials()
    return AWSV4SignerAuth(credentials, AWS_REGION, "aoss")


def create_opensearch_client():
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_ENDPOINT, "port": 443}],
        http_auth=get_aws_auth(),
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )


def setup_opensearch_index():
    client = create_opensearch_client()
    mappings = {
        "mappings": {
            "properties": {
                "node_id": {"type": "keyword"},
                "node_type": {"type": "keyword"},
                "content": {"type": "text"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": OPENSEARCH_EMBEDDING_DIM,
                    "method": {
                        "name": "hnsw",
                        "engine": "nmslib",
                        "space_type": "cosinesimil",
                    },
                },
                "paper_url": {"type": "keyword"},
                "section_id": {"type": "keyword"},
                "section_title": {"type": "text"},
                "block_type": {"type": "keyword"},
                "source": {"type": "keyword"},
            },
        },
        "settings": {"index": {"knn": True}},
    }
    client.indices.create(index=OPENSEARCH_INDEX, body=mappings)


def extract_neptune_data(graph):
    papers = graph._query(
        "MATCH (p:Paper) RETURN p.url AS paper_url"
    ).get("results", [])

    sections = graph._query(
        "MATCH (s:Section)-[:PART_OF]->(p:Paper) "
        "RETURN s.id AS section_id, s.title AS section_title, "
        "s.level AS section_level, p.url AS paper_url"
    ).get("results", [])

    blocks = graph._query(
        "MATCH (b:Block)-[:CONTAINED_IN]->(s:Section)-[:PART_OF]->(p:Paper) "
        "RETURN b.id AS block_id, b.text AS block_text, b.type AS block_type, "
        "s.id AS section_id, s.title AS section_title, p.url AS paper_url"
    ).get("results", [])

    cited_blocks = graph._query(
        "MATCH (b:Block)-[:CONTAINED_IN_CITED]->(p:Paper) "
        "RETURN b.id AS block_id, b.text AS block_text, b.type AS block_type, "
        "p.url AS paper_url"
    ).get("results", [])

    return papers, sections, blocks, cited_blocks


def index_papers_to_opensearch(graph=None):
    if graph is None:
        graph = NeptuneGraph()
    papers, sections, blocks, cited_blocks = extract_neptune_data(graph)
    embedder = BedrockEmbedder()
    client = create_opensearch_client()

    for paper in papers:
        content = f"Research paper: {paper['paper_url']}"
        doc = {
            "node_id": paper["paper_url"],
            "node_type": "Paper",
            "content": content,
            "paper_url": paper["paper_url"],
            "embedding": embedder.embed(content),
            "source": "primary",
        }
        client.index(index=OPENSEARCH_INDEX, body=doc)

    for section in sections:
        doc = {
            "node_id": section["section_id"],
            "node_type": "Section",
            "content": section["section_title"],
            "section_id": section["section_id"],
            "section_title": section["section_title"],
            "paper_url": section["paper_url"],
            "embedding": embedder.embed(section["section_title"]),
            "source": "primary",
        }
        client.index(index=OPENSEARCH_INDEX, body=doc)

    for block in blocks:
        doc = {
            "node_id": block["block_id"],
            "node_type": "Block",
            "content": block["block_text"],
            "block_type": block["block_type"],
            "section_id": block["section_id"],
            "section_title": block["section_title"],
            "paper_url": block["paper_url"],
            "embedding": embedder.embed(block["block_text"]),
            "source": "primary",
        }
        client.index(index=OPENSEARCH_INDEX, body=doc)

    for block in cited_blocks:
        doc = {
            "node_id": block["block_id"],
            "node_type": "Block",
            "content": block["block_text"],
            "block_type": block["block_type"],
            "paper_url": block["paper_url"],
            "embedding": embedder.embed(block["block_text"]),
            "source": "cited_paper",
        }
        client.index(index=OPENSEARCH_INDEX, body=doc)

    client.indices.refresh(index=OPENSEARCH_INDEX)


def search_opensearch(query_embedding, top_k=5):
    client = create_opensearch_client()
    knn_query = {
        "size": top_k,
        "query": {
            "knn": {
                "embedding": {
                    "vector": query_embedding,
                    "k": top_k,
                }
            }
        },
    }
    response = client.search(index=OPENSEARCH_INDEX, body=knn_query)
    return response["hits"]["hits"]


def get_relevant_context_from_neptune(search_results, graph):
    context_items = []
    citation_ids = set()

    for hit in search_results:
        source = hit["_source"]
        node_type = source["node_type"]
        node_id = source["node_id"]

        if node_type == "Block":
            result = graph._query(
                "MATCH (b:Block {id: $block_id}) "
                "OPTIONAL MATCH (b)-[:CONTAINED_IN]->(s:Section)-[:PART_OF]->(p:Paper) "
                "OPTIONAL MATCH (b)-[:CONTAINED_IN_CITED]->(cp:Paper) "
                "OPTIONAL MATCH (b)-[:CITES]->(c:Citation) "
                "RETURN b.id AS block_id, b.text AS block_text, b.type AS block_type, "
                "b.source AS source, "
                "s.id AS section_id, s.title AS section_title, "
                "COALESCE(p.url, cp.url) AS paper_url, "
                "COLLECT(DISTINCT {id: c.id, title: c.title, authors: c.authors, date: c.date}) AS citations",
                {"block_id": node_id},
            ).get("results", [])

            if result:
                r = result[0]
                item = {
                    "type": "Block",
                    "id": r["block_id"],
                    "text": r["block_text"],
                    "block_type": r["block_type"],
                    "section_id": r.get("section_id"),
                    "section_title": r.get("section_title"),
                    "paper_url": r["paper_url"],
                    "source": r.get("source") or "primary",
                    "citations": [c for c in r.get("citations", []) if c.get("id")],
                }
                context_items.append(item)
                for c in item["citations"]:
                    if c["id"]:
                        citation_ids.add(c["id"])

        elif node_type == "Section":
            result = graph._query(
                "MATCH (s:Section {id: $section_id})-[:PART_OF]->(p:Paper) "
                "OPTIONAL MATCH (b:Block)-[:CONTAINED_IN]->(s) "
                "OPTIONAL MATCH (b)-[:CITES]->(c:Citation) "
                "RETURN s.id AS section_id, s.title AS section_title, p.url AS paper_url, "
                "COLLECT(DISTINCT {id: b.id, text: b.text, type: b.type}) AS blocks, "
                "COLLECT(DISTINCT {id: c.id, title: c.title, authors: c.authors, date: c.date}) AS citations",
                {"section_id": node_id},
            ).get("results", [])

            if result:
                r = result[0]
                item = {
                    "type": "Section",
                    "id": r["section_id"],
                    "title": r["section_title"],
                    "paper_url": r["paper_url"],
                    "blocks": [b for b in r.get("blocks", []) if b.get("id")],
                    "citations": [c for c in r.get("citations", []) if c.get("id")],
                }
                context_items.append(item)
                for c in item["citations"]:
                    if c["id"]:
                        citation_ids.add(c["id"])

    citations = []
    for cid in citation_ids:
        result = graph._query(
            "MATCH (c:Citation {id: $cid}) "
            "RETURN c.id AS id, c.title AS title, c.authors AS authors, c.date AS date",
            {"cid": cid},
        ).get("results", [])
        if result:
            citations.append(result[0])

    return {"context_items": context_items, "citations": citations}


def format_context_for_claude(context_data):
    parts = ["### Relevant Research Paper Context:\n"]

    for item in context_data["context_items"]:
        if item["type"] == "Block":
            source_tag = " (from cited paper)" if item.get("source") == "cited_paper" else ""
            parts.append(f"## Block from Section: {item['section_title']}{source_tag}")
            parts.append(f"**Type:** {item['block_type']}")
            parts.append(f"**Content:**\n{item['text']}\n")
            if item.get("citations"):
                refs = ", ".join(f"[{c['id']}]" for c in item["citations"])
                parts.append(f"**Citations:** {refs}\n")
        elif item["type"] == "Section":
            parts.append(f"## Section: {item['title']}")
            for block in item.get("blocks", []):
                parts.append(f"**{block['type']}:** {block['text']}\n")

    if context_data["citations"]:
        parts.append("### References:\n")
        for c in context_data["citations"]:
            parts.append(f"[{c['id']}] {c['authors']}, \"{c['title']}\", {c['date']}")

    return "\n".join(parts)


def query_claude(user_query, context):
    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    prompt = (
        "You are an AI research assistant helping with academic papers.\n"
        "Answer the following question using the provided research paper context.\n"
        "If the answer cannot be found in the context, state that clearly.\n"
        "Always cite your sources using the citation IDs.\n\n"
        f"### Context:\n{context}\n\n"
        f"### Question:\n{user_query}"
    )

    response = client.invoke_model(
        modelId=BEDROCK_LLM_MODEL,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )
    return json.loads(response["body"].read())["content"][0]["text"]


def process_rag_query(user_query):
    embedder = BedrockEmbedder()
    graph = NeptuneGraph()

    query_embedding = embedder.embed(user_query)
    search_results = search_opensearch(query_embedding)
    context_data = get_relevant_context_from_neptune(search_results, graph)
    formatted_context = format_context_for_claude(context_data)
    response = query_claude(user_query, formatted_context)

    return {
        "query": user_query,
        "response": response,
        "formatted_context": formatted_context,
        "citations": context_data["citations"],
        "search_results": search_results,
    }
