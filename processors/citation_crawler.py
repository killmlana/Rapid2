import time
import logging

import requests

from config.settings import SEMANTIC_SCHOLAR_API_KEY, MAX_CITATION_DEPTH, MAX_CITED_PAPERS
from grobid_client import GrobidClient
from vila_parser import VilaClient
from processors.neo4j_manager import Neo4jGraph

logger = logging.getLogger(__name__)

S2_API = "https://api.semanticscholar.org/graph/v1"


class CitationCrawler:
    def __init__(self, neo4j: Neo4jGraph, grobid: GrobidClient = None, vila: VilaClient = None):
        self.neo4j = neo4j
        self.grobid = grobid or GrobidClient()
        self.vila = vila or VilaClient()
        self.s2_headers = {}
        if SEMANTIC_SCHOLAR_API_KEY:
            self.s2_headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
        self.processed_urls = set()

    def find_paper_on_s2(self, title, authors=None):
        query = title
        if authors and len(authors) > 0:
            first_author = authors[0].split()[-1] if isinstance(authors[0], str) else ""
            if first_author:
                query = f"{first_author} {title}"

        resp = requests.get(
            f"{S2_API}/paper/search",
            params={"query": query, "limit": 3, "fields": "title,openAccessPdf,externalIds"},
            headers=self.s2_headers,
            timeout=30,
        )
        if resp.status_code == 429:
            time.sleep(5)
            return self.find_paper_on_s2(title, authors)
        if resp.status_code != 200:
            return None

        data = resp.json()
        for paper in data.get("data", []):
            if paper.get("openAccessPdf", {}) and paper["openAccessPdf"].get("url"):
                return {
                    "url": paper["openAccessPdf"]["url"],
                    "title": paper.get("title", ""),
                    "s2_id": paper.get("paperId", ""),
                }

            arxiv_id = (paper.get("externalIds") or {}).get("ArXiv")
            if arxiv_id:
                return {
                    "url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                    "title": paper.get("title", ""),
                    "s2_id": paper.get("paperId", ""),
                }

        return None

    def extract_relevant_sections(self, vila_df, citation_mentions):
        relevant_blocks = []
        if vila_df is None or vila_df.empty:
            return relevant_blocks

        mention_terms = set()
        for mention in citation_mentions:
            for word in str(mention).lower().split():
                if len(word) > 3:
                    mention_terms.add(word)

        for _, row in vila_df.iterrows():
            text = str(row.get("text", ""))
            if not text or text == "nan":
                continue

            if row.get("type") in ("Abstract", "Section"):
                relevant_blocks.append({"text": text, "type": row["type"]})
                continue

            text_lower = text.lower()
            if any(term in text_lower for term in mention_terms):
                relevant_blocks.append({"text": text, "type": row.get("type", "Paragraph")})

        return relevant_blocks[:50]

    def crawl_citations(self, parent_paper_url, citations, depth=0):
        if depth >= MAX_CITATION_DEPTH:
            return

        processed_count = 0
        for citation in citations:
            if processed_count >= MAX_CITED_PAPERS:
                break

            title = citation.get("title")
            if not title:
                continue

            logger.info("Searching for cited paper: %s", title)
            paper_info = self.find_paper_on_s2(title, citation.get("authors"))

            if not paper_info:
                logger.info("Could not find PDF for: %s", title)
                continue

            pdf_url = paper_info["url"]
            if pdf_url in self.processed_urls:
                continue
            self.processed_urls.add(pdf_url)

            try:
                vila_df = self.vila.parse_pdf(pdf_url)
                relevant_blocks = self.extract_relevant_sections(
                    vila_df, citation.get("mentions", [])
                )

                if relevant_blocks:
                    self.neo4j.store_cited_paper_context(
                        parent_paper_url, pdf_url, relevant_blocks
                    )
                    logger.info(
                        "Stored %d relevant blocks from cited paper: %s",
                        len(relevant_blocks), title,
                    )

                processed_count += 1
                time.sleep(1)

            except Exception:
                logger.exception("Failed to process cited paper: %s", title)
                continue

    def crawl_paper_citations(self, paper_url):
        citations = self.neo4j.get_paper_citations(paper_url)
        logger.info("Found %d citations to crawl for %s", len(citations), paper_url)
        self.crawl_citations(paper_url, citations)
