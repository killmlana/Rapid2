import os
import json
import boto3
import botocore
import pandas as pd
from neo4j import GraphDatabase
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# ========== CONFIGURATION ==========
# AWS Configuration
AWS_REGION = "us-west-2" 
BEDROCK_MODEL_ID = "amazon.titan-embed-text-v1"
OPENSEARCH_ENDPOINT = "8geb4aspg24cbllfp4ob.us-west-2.aoss.amazonaws.com"
OPENSEARCH_INDEX = "papers"
OPENSEARCH_EMBEDDING_DIMENSION = 1536  # Titan v1 embedding size


# Neo4j Configuration
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "password"

# Claude Configuration
CLAUDE_MODEL = "anthropic.claude-3-5-sonnet-20241022-v2:0"

# ========== UTILITY FUNCTIONS ==========

def get_aws_auth(region):
    """Create AWS authentication for OpenSearch"""
    credentials = boto3.Session().get_credentials()
    return AWSV4SignerAuth(credentials, region, 'aoss')

def create_opensearch_client():
    """Create and return an OpenSearch client"""
    auth = get_aws_auth(AWS_REGION)
    return OpenSearch(
        hosts=[{'host': OPENSEARCH_ENDPOINT, 'port': 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )

def create_bedrock_runtime():
    """Create and return a Bedrock runtime client"""
    return boto3.client('bedrock-runtime', region_name=AWS_REGION)

def create_neo4j_driver():
    """Create and return a Neo4j driver"""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

# ========== SETUP OPENSEARCH INDEX ==========

def setup_opensearch_index():
    """Create OpenSearch index with appropriate mapping for vector search"""
    client = create_opensearch_client()
    
    mappings = {
        "mappings": {
            "properties": {
                "node_id": {"type": "keyword"},
                "node_type": {"type": "keyword"},
                "content": {"type": "text"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": OPENSEARCH_EMBEDDING_DIMENSION,
                    "method": {
                            "name": "hnsw",
                            "engine": "nmslib",
                            "space_type": "cosinesimil"
                        }
                },
                "paper_url": {"type": "keyword"},
                "section_id": {"type": "keyword"},
                "section_title": {"type": "text"},
                "block_type": {"type": "keyword"}
            }
        },
        "settings": {
            "index": {
                "knn": True
            }
        }
    }
    
    client.indices.create(index=OPENSEARCH_INDEX, body=mappings)
    print(f"Created index {OPENSEARCH_INDEX}")

# ========== CREATE EMBEDDINGS AND INDEX CONTENT ==========

def generate_embedding(text, bedrock_client):
    """Generate embeddings using AWS Bedrock Titan model"""
    request_body = {
        "inputText": text
    }
    
    response = bedrock_client.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(request_body)
    )
    
    response_body = json.loads(response['body'].read())
    return response_body['embedding']

def extract_neo4j_data():
    """Extract data from Neo4j to be indexed in OpenSearch"""
    driver = create_neo4j_driver()
    
    with driver.session() as session:
        # Get Paper nodes
        papers = session.run("""
        MATCH (p:Paper)
        RETURN p.url AS paper_url
        """).data()
        
        # Get Section nodes
        sections = session.run("""
        MATCH (s:Section)-[:PART_OF]->(p:Paper)
        RETURN s.id AS section_id, s.title AS section_title, 
               s.level AS section_level, p.url AS paper_url
        """).data()
        
        # Get Block nodes
        blocks = session.run("""
        MATCH (b:Block)-[:CONTAINED_IN]->(s:Section)-[:PART_OF]->(p:Paper)
        RETURN b.id AS block_id, b.text AS block_text, b.type AS block_type,
               s.id AS section_id, s.title AS section_title, p.url AS paper_url
        """).data()
        
    return papers, sections, blocks

def index_papers_to_opensearch():
    """Extract data from Neo4j and index it to OpenSearch with embeddings"""
    papers, sections, blocks = extract_neo4j_data()
    
    bedrock_client = create_bedrock_runtime()
    opensearch_client = create_opensearch_client()
    
    # Index Paper nodes
    for paper in papers:
        doc = {
            "node_id": paper["paper_url"],
            "node_type": "Paper",
            "content": f"Research paper with URL: {paper['paper_url']}",
            "paper_url": paper["paper_url"],
            "embedding": generate_embedding(f"Research paper with URL: {paper['paper_url']}", bedrock_client)
        }
        opensearch_client.index(index=OPENSEARCH_INDEX, body=doc)
    
    # Index Section nodes
    for section in sections:
        doc = {
            "node_id": section["section_id"],
            "node_type": "Section",
            "content": f"{section['section_title']}",
            "section_id": section["section_id"],
            "section_title": section["section_title"],
            "paper_url": section["paper_url"],
            "embedding": generate_embedding(section["section_title"], bedrock_client)
        }
        opensearch_client.index(index=OPENSEARCH_INDEX, body=doc)
    
    # Index Block nodes
    for block in blocks:
        doc = {
            "node_id": block["block_id"],
            "node_type": "Block",
            "content": block["block_text"],
            "block_type": block["block_type"],
            "section_id": block["section_id"],
            "section_title": block["section_title"],
            "paper_url": block["paper_url"],
            "embedding": generate_embedding(block["block_text"], bedrock_client)
        }
        opensearch_client.index(index=OPENSEARCH_INDEX, body=doc)
    
    # Force refresh to make the documents available for search
    opensearch_client.indices.refresh(index=OPENSEARCH_INDEX)
    print("Indexed all Neo4j nodes to OpenSearch")

# ========== QUERY PROCESSING ==========

def vectorize_query(query_text, bedrock_client):
    """Generate embedding for the user query"""
    return generate_embedding(query_text, bedrock_client)

def search_opensearch(query_embedding, top_k=5):
    """Search OpenSearch for relevant content"""
    client = create_opensearch_client()
    
    knn_query = {
        "size": top_k,
        "query": {
            "knn": {
                "embedding": {
                    "vector": query_embedding,
                    "k": top_k
                }
            }
        }
    }
    
    response = client.search(index=OPENSEARCH_INDEX, body=knn_query)
    return response["hits"]["hits"]

def get_relevant_context_from_neo4j(search_results, neo4j_driver):
    """Retrieve detailed context from Neo4j based on search results"""
    context_items = []
    citation_ids = set()
    
    with neo4j_driver.session() as session:
        for hit in search_results:
            source = hit["_source"]
            node_type = source["node_type"]
            node_id = source["node_id"]
            
            if node_type == "Block":
                # Get block details with citations
                block_result = session.run("""
                MATCH (b:Block {id: $block_id})-[:CONTAINED_IN]->(s:Section)-[:PART_OF]->(p:Paper)
                OPTIONAL MATCH (b)-[:CITES]->(c:Citation)
                RETURN b.id AS block_id, b.text AS block_text, b.type AS block_type, 
                       s.id AS section_id, s.title AS section_title, p.url AS paper_url,
                       COLLECT(DISTINCT {id: c.id, title: c.title, authors: c.authors, date: c.date}) AS citations
                """, block_id=node_id).single()
                
                if block_result:
                    context_item = {
                        "type": "Block",
                        "id": block_result["block_id"],
                        "text": block_result["block_text"],
                        "block_type": block_result["block_type"],
                        "section_id": block_result["section_id"],
                        "section_title": block_result["section_title"],
                        "paper_url": block_result["paper_url"],
                        "citations": [c for c in block_result["citations"] if c["id"] is not None]
                    }
                    context_items.append(context_item)
                    
                    # Add citation IDs to the set
                    for citation in context_item["citations"]:
                        if citation["id"]:
                            citation_ids.add(citation["id"])
            
            elif node_type == "Section":
                # Get section details with blocks
                section_result = session.run("""
                MATCH (s:Section {id: $section_id})-[:PART_OF]->(p:Paper)
                OPTIONAL MATCH (b:Block)-[:CONTAINED_IN]->(s)
                OPTIONAL MATCH (b)-[:CITES]->(c:Citation)
                RETURN s.id AS section_id, s.title AS section_title, p.url AS paper_url,
                       COLLECT(DISTINCT {id: b.id, text: b.text, type: b.type}) AS blocks,
                       COLLECT(DISTINCT {id: c.id, title: c.title, authors: c.authors, date: c.date}) AS citations
                """, section_id=node_id).single()
                
                if section_result:
                    context_item = {
                        "type": "Section",
                        "id": section_result["section_id"],
                        "title": section_result["section_title"],
                        "paper_url": section_result["paper_url"],
                        "blocks": [b for b in section_result["blocks"] if b["id"] is not None],
                        "citations": [c for c in section_result["citations"] if c["id"] is not None]
                    }
                    context_items.append(context_item)
                    
                    # Add citation IDs to the set
                    for citation in context_item["citations"]:
                        if citation["id"]:
                            citation_ids.add(citation["id"])
        
        # Get full citation details
        citations = []
        for citation_id in citation_ids:
            citation_result = session.run("""
            MATCH (c:Citation {id: $citation_id})
            RETURN c.id AS id, c.title AS title, c.authors AS authors, c.date AS date
            """, citation_id=citation_id).single()
            
            if citation_result:
                citations.append({
                    "id": citation_result["id"],
                    "title": citation_result["title"],
                    "authors": citation_result["authors"],
                    "date": citation_result["date"]
                })
    
    return {
        "context_items": context_items,
        "citations": citations
    }

def format_context_for_claude(context_data):
    """Format the retrieved context into a prompt for Claude"""
    formatted_context = "### Relevant Research Paper Context:\n\n"
    
    # Add context items
    for item in context_data["context_items"]:
        if item["type"] == "Block":
            formatted_context += f"## Block from Section: {item['section_title']}\n"
            formatted_context += f"**Type:** {item['block_type']}\n"
            formatted_context += f"**Content:**\n{item['text']}\n\n"
            
            # Add citation references inline
            if item.get("citations"):
                formatted_context += "**Citations:** "
                citation_refs = [f"[{c['id']}]" for c in item["citations"]]
                formatted_context += ", ".join(citation_refs) + "\n\n"
        
        elif item["type"] == "Section":
            formatted_context += f"## Section: {item['title']}\n"
            
            # Add blocks from this section
            for block in item.get("blocks", []):
                formatted_context += f"**{block['type']}:** {block['text']}\n\n"
    
    # Add citation details at the end
    if context_data["citations"]:
        formatted_context += "### References:\n\n"
        for citation in context_data["citations"]:
            formatted_context += f"[{citation['id']}] {citation['authors']}, \"{citation['title']}\", {citation['date']}\n"
    
    return formatted_context

def query_claude(user_query, context, claude_client):
    prompt = f"""
You are an AI research assistant helping with academic papers.
Please answer the following question using the provided research paper context.
If the answer cannot be found in the context, please state that clearly.
Always cite your sources using the citation IDs when providing information.

### Context:
{context}

### User Question:
{user_query}

### Response:
"""
    
    response = claude_client.invoke_model(
        modelId=CLAUDE_MODEL,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "temperature": 0,
            "system": "You are an AI research assistant that helps users retrieve information from academic papers. Respond with accurate information and always cite your sources.",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        })
    )
    
    return json.loads(response['body'].read())['content'][0]['text']

# ========== MAIN RAG QUERY FUNCTION ==========

def process_rag_query(user_query):
    """Process a user query through the entire RAG pipeline"""
    # Initialize clients
    bedrock_client = create_bedrock_runtime()
    neo4j_driver = create_neo4j_driver()
    claude_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
    
    # 1. Vectorize the query
    query_embedding = vectorize_query(user_query, bedrock_client)
    
    # 2. Search OpenSearch
    search_results = search_opensearch(query_embedding)
    
    # 3. Retrieve context from Neo4j
    context_data = get_relevant_context_from_neo4j(search_results, neo4j_driver)
    
    # 4. Format context for Claude
    formatted_context = format_context_for_claude(context_data)
    
    # 5. Query Claude with context
    claude_response = query_claude(user_query, formatted_context, claude_client)
    
    return {
        "query": user_query,
        "response": claude_response,
        "formatted_context": formatted_context,
        "citations": context_data["citations"],
        "search_results": search_results
    }

# ========== RUNNING THE PIPELINE ==========

if __name__ == "__main__":
    # Setup OpenSearch index (only needs to be run once)
    """setup_opensearch_index()
    
    # Index Neo4j data to OpenSearch (run periodically to keep data in sync)
    index_papers_to_opensearch()"""
    
    # Example query
    user_query = "Which papers cited in this work relate to transformers?"
    result = process_rag_query(user_query)
    
    print(f"User Query: {result['query']}")
    print(f"formatted_context: {result['formatted_context']}")
    print(f"Claude Response: {result['response']}")
    print(f"Citations Used: {len(result['citations'])}")