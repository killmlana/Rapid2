import logging
import sys

from vila_parser import VilaClient
from grobid_client import GrobidClient
from processors.neo4j_manager import Neo4jGraph
from processors.citation_crawler import CitationCrawler
from processors.opensearch_client import (
    setup_opensearch_index,
    index_papers_to_opensearch,
    process_rag_query,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def process_research_paper(pdf_url, crawl_citations=True):
    vila = VilaClient()
    grobid = GrobidClient()
    neo4j = Neo4jGraph()

    logger.info("Parsing PDF with VILA: %s", pdf_url)
    vila_df = vila.parse_pdf(pdf_url)

    logger.info("Extracting citations with GROBID")
    xml_content = grobid.process_pdf(pdf_url)
    citations = grobid.parse_citations(xml_content)
    logger.info("Found %d citations", len(citations))

    logger.info("Building knowledge graph")
    neo4j.create_schema()
    neo4j.store_paper(vila_df, citations, pdf_url)

    if crawl_citations:
        logger.info("Crawling cited papers for additional context")
        crawler = CitationCrawler(neo4j, grobid, vila)
        crawler.crawl_paper_citations(pdf_url)

    neo4j.close()
    logger.info("Paper processing complete: %s", pdf_url)


def process_batch(pdf_urls, crawl_citations=True):
    for i, url in enumerate(pdf_urls):
        logger.info("Processing paper %d/%d: %s", i + 1, len(pdf_urls), url)
        try:
            process_research_paper(url, crawl_citations=crawl_citations)
        except Exception:
            logger.exception("Failed to process: %s", url)
            continue

    logger.info("Indexing all papers to OpenSearch")
    setup_opensearch_index()
    index_papers_to_opensearch()
    logger.info("Batch processing complete")


def query(user_query):
    result = process_rag_query(user_query)
    print(f"\nQuery: {result['query']}")
    print(f"\nContext:\n{result['formatted_context']}")
    print(f"\nResponse:\n{result['response']}")
    print(f"\nCitations used: {len(result['citations'])}")
    return result


if __name__ == "__main__":
    papers = [
        "https://arxiv.org/pdf/2106.00676.pdf",
    ]

    if "--query" in sys.argv:
        idx = sys.argv.index("--query")
        user_query = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "What are the main findings?"
        query(user_query)
    else:
        crawl = "--no-crawl" not in sys.argv
        process_batch(papers, crawl_citations=crawl)

        user_query = "What are the main findings in the research paper?"
        query(user_query)
