import tempfile
import os

import pandas as pd
import pytest

from processors.pdf_processor import PDFProcessor


@pytest.fixture
def sample_csv(tmp_path):
    df = pd.DataFrame([
        {"text": "My Paper Title", "type": "Title", "block_type": "Text", "page": 1,
         "x1": 0.1, "y1": 0.05, "x2": 0.9, "y2": 0.1},
        {"text": "Author Name", "type": "Author", "block_type": "Text", "page": 1,
         "x1": 0.1, "y1": 0.11, "x2": 0.9, "y2": 0.15},
        {"text": "1 Introduction", "type": "Section", "block_type": "Text", "page": 1,
         "x1": 0.1, "y1": 0.2, "x2": 0.9, "y2": 0.25},
        {"text": "This is the introduction.", "type": "Paragraph", "block_type": "Text", "page": 1,
         "x1": 0.1, "y1": 0.26, "x2": 0.9, "y2": 0.35},
        {"text": "1.1 Background", "type": "Section", "block_type": "Text", "page": 1,
         "x1": 0.1, "y1": 0.36, "x2": 0.9, "y2": 0.4},
        {"text": "Background content here.", "type": "Paragraph", "block_type": "Text", "page": 1,
         "x1": 0.1, "y1": 0.41, "x2": 0.9, "y2": 0.5},
        {"text": "A figure caption", "type": "Paragraph", "block_type": "Figure", "page": 2,
         "x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.5},
        {"text": "This is a footnote.", "type": "Footnote", "block_type": "Text", "page": 2,
         "x1": 0.1, "y1": 0.9, "x2": 0.9, "y2": 0.95},
    ])
    path = tmp_path / "test.csv"
    df.to_csv(path, index=False)
    return str(path)


class TestPDFProcessor:
    def test_parse_extracts_metadata(self, sample_csv):
        proc = PDFProcessor()
        doc = proc.parse_vila_csv(sample_csv)
        assert doc["metadata"]["title"] == "My Paper Title"
        assert doc["metadata"]["authors"] == "Author Name"

    def test_parse_extracts_sections(self, sample_csv):
        proc = PDFProcessor()
        doc = proc.parse_vila_csv(sample_csv)
        assert len(doc["sections"]) >= 1
        intro = doc["sections"][0]
        assert "Introduction" in intro["title"]

    def test_parse_subsection_hierarchy(self, sample_csv):
        proc = PDFProcessor()
        doc = proc.parse_vila_csv(sample_csv)
        intro = next(s for s in doc["sections"] if "Introduction" in s.get("title", ""))
        assert len(intro["subsections"]) == 1
        assert "Background" in intro["subsections"][0]["title"]

    def test_parse_extracts_figures(self, sample_csv):
        proc = PDFProcessor()
        doc = proc.parse_vila_csv(sample_csv)
        assert len(doc["figures"]) == 1
        assert doc["figures"][0]["page"] == 2

    def test_parse_extracts_footnotes(self, sample_csv):
        proc = PDFProcessor()
        doc = proc.parse_vila_csv(sample_csv)
        assert len(doc["footnotes"]) == 1
        assert "footnote" in doc["footnotes"][0]

    def test_content_assigned_to_section(self, sample_csv):
        proc = PDFProcessor()
        doc = proc.parse_vila_csv(sample_csv)
        intro = doc["sections"][0]
        assert any("introduction" in b["text"].lower() for b in intro["blocks"])
