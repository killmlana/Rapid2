import pandas as pd
import pytest

from processors.citation_crawler import CitationCrawler


class FakeGraph:
    def __init__(self):
        self.stored = []
        self.citations_response = []

    def get_paper_citations(self, paper_url):
        return self.citations_response

    def store_cited_paper_context(self, parent_url, cited_url, blocks):
        self.stored.append({
            "parent_url": parent_url,
            "cited_url": cited_url,
            "blocks": blocks,
        })


class TestCitationCrawler:
    def test_extract_relevant_sections_abstract(self):
        crawler = CitationCrawler(graph=FakeGraph())
        df = pd.DataFrame([
            {"text": "This paper studies transformers.", "type": "Abstract", "page": 1,
             "x1": 0, "y1": 0, "x2": 1, "y2": 1},
            {"text": "Introduction", "type": "Section", "page": 1,
             "x1": 0, "y1": 0.1, "x2": 1, "y2": 0.15},
            {"text": "Some irrelevant content about biology.", "type": "Paragraph", "page": 1,
             "x1": 0, "y1": 0.2, "x2": 1, "y2": 0.3},
        ])

        blocks = crawler.extract_relevant_sections(df, ["transformers attention"])
        types = [b["type"] for b in blocks]
        assert "Abstract" in types
        assert "Section" in types

    def test_extract_relevant_sections_mention_matching(self):
        crawler = CitationCrawler(graph=FakeGraph())
        df = pd.DataFrame([
            {"text": "We propose a novel attention mechanism.", "type": "Paragraph", "page": 1,
             "x1": 0, "y1": 0, "x2": 1, "y2": 1},
            {"text": "Unrelated content about cooking.", "type": "Paragraph", "page": 2,
             "x1": 0, "y1": 0, "x2": 1, "y2": 1},
        ])

        blocks = crawler.extract_relevant_sections(df, ["attention mechanism"])
        assert len(blocks) == 1
        assert "attention" in blocks[0]["text"].lower()

    def test_extract_relevant_sections_empty_df(self):
        crawler = CitationCrawler(graph=FakeGraph())
        blocks = crawler.extract_relevant_sections(pd.DataFrame(), ["anything"])
        assert blocks == []

    def test_extract_relevant_sections_none_df(self):
        crawler = CitationCrawler(graph=FakeGraph())
        blocks = crawler.extract_relevant_sections(None, ["anything"])
        assert blocks == []

    def test_extract_relevant_sections_limit(self):
        crawler = CitationCrawler(graph=FakeGraph())
        rows = [
            {"text": f"Attention block {i}", "type": "Paragraph", "page": 1,
             "x1": 0, "y1": i, "x2": 1, "y2": i + 1}
            for i in range(100)
        ]
        df = pd.DataFrame(rows)
        blocks = crawler.extract_relevant_sections(df, ["attention"])
        assert len(blocks) <= 50
