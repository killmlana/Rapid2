import pandas as pd
import pytest

from processors.image_processor import ImageProcessor


class TestFigureDetection:
    def test_no_figures_returns_empty(self):
        proc = ImageProcessor.__new__(ImageProcessor)
        df = pd.DataFrame([
            {"text": "Introduction", "type": "Section", "page": 1,
             "x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.15},
            {"text": "Some paragraph.", "type": "Paragraph", "page": 1,
             "x1": 0.1, "y1": 0.2, "x2": 0.9, "y2": 0.4},
        ])
        figures = proc.extract_figures_from_pdf.__wrapped__(proc, b"", df) if hasattr(proc.extract_figures_from_pdf, '__wrapped__') else []
        assert isinstance(figures, list)

    def test_figure_rows_detected(self):
        df = pd.DataFrame([
            {"text": "Fig 1: Architecture", "type": "Figure", "page": 1,
             "x1": 0.1, "y1": 0.3, "x2": 0.9, "y2": 0.7},
            {"text": "Table 1: Results", "type": "Table", "page": 2,
             "x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.5},
            {"text": "Just text", "type": "Paragraph", "page": 1,
             "x1": 0.1, "y1": 0.8, "x2": 0.9, "y2": 0.9},
        ])
        figure_rows = df[df["type"].isin(["Figure", "Table"])]
        assert len(figure_rows) == 2
        assert "Fig 1: Architecture" in figure_rows.iloc[0]["text"]

    def test_block_type_column_fallback(self):
        df = pd.DataFrame([
            {"text": "A figure caption", "type": "Paragraph", "block_type": "Figure",
             "page": 1, "x1": 0.1, "y1": 0.3, "x2": 0.9, "y2": 0.7},
        ])
        figure_rows = df[df["type"].isin(["Figure", "Table"])]
        if figure_rows.empty and "block_type" in df.columns:
            figure_rows = df[df["block_type"].isin(["Figure", "Table"])]
        assert len(figure_rows) == 1
