import logging
import sys

from vila_parser import VilaClient
from grobid_client import GrobidClient
from processors.neptune_client import NeptuneGraph
from processors.citation_crawler import CitationCrawler
from processors.annas_client import AnnasArchiveClient
from processors.opensearch_client import (
    setup_opensearch_index,
    index_papers_to_opensearch,
    process_rag_query,
)
from config.settings import ANNAS_OPENSEARCH_ENDPOINT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def process_research_paper(pdf_url, crawl_citations=True):
    vila = VilaClient()
    grobid = GrobidClient()
    graph = NeptuneGraph()

    logger.info("Parsing PDF with VILA: %s", pdf_url)
    vila_df = vila.parse_pdf(pdf_url)

    logger.info("Extracting citations with GROBID")
    xml_content = grobid.process_pdf(pdf_url)
    citations = grobid.parse_citations(xml_content)
    logger.info("Found %d citations", len(citations))

    logger.info("Building knowledge graph in Neptune")
    graph.store_paper(vila_df, citations, pdf_url)

    if crawl_citations:
        logger.info("Crawling cited papers for additional context")
        crawler = CitationCrawler(graph, grobid, vila)
        crawler.crawl_paper_citations(pdf_url)

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


def search_and_process(topic, max_papers=5, crawl_citations=True, filters=None):
    annas = AnnasArchiveClient(ANNAS_OPENSEARCH_ENDPOINT)
    papers = annas.search_papers(topic, filters=filters, max_results=max_papers)

    if not papers:
        logger.info("No papers found for: %s", topic)
        return []

    logger.info("Found %d papers for topic: %s", len(papers), topic)
    pdf_urls = []
    for paper in papers:
        url = annas.resolve_download_url(paper)
        if url:
            pdf_urls.append(url)
            logger.info("  - %s (%s)", paper.get("title", "Unknown"), url)

    if pdf_urls:
        process_batch(pdf_urls, crawl_citations=crawl_citations)

    return pdf_urls


def query(user_query):
    result = process_rag_query(user_query)
    print(f"\nQuery: {result['query']}")
    print(f"\nContext:\n{result['formatted_context']}")
    print(f"\nResponse:\n{result['response']}")
    print(f"\nCitations used: {len(result['citations'])}")
    return result


if __name__ == "__main__":
    if "--search" in sys.argv:
        idx = sys.argv.index("--search")
        topic = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "transformers attention mechanism"
        max_papers = 5
        if "--max" in sys.argv:
            max_papers = int(sys.argv[sys.argv.index("--max") + 1])
        crawl = "--no-crawl" not in sys.argv
        search_and_process(topic, max_papers=max_papers, crawl_citations=crawl)

    elif "--query" in sys.argv:
        idx = sys.argv.index("--query")
        user_query = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "What are the main findings?"
        query(user_query)

    elif "--url" in sys.argv:
        idx = sys.argv.index("--url")
        urls = sys.argv[idx + 1 :]
        urls = [u for u in urls if u.startswith("http")]
        crawl = "--no-crawl" not in sys.argv
        process_batch(urls, crawl_citations=crawl)

    else:
        print("Usage:")
        print("  python main.py --search 'topic' [--max 5] [--no-crawl]")
        print("  python main.py --url https://arxiv.org/pdf/... [--no-crawl]")
        print("  python main.py --query 'your question'")
