import pandas as pd
import pytest

from processors.neptune_client import NeptuneGraph


class TestDoubleColumnDetection:
    def test_single_column(self):
        df = pd.DataFrame([
            {"x1": 0.1, "y1": 0.0, "x2": 0.9, "y2": 0.1},
            {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.2},
            {"x1": 0.1, "y1": 0.2, "x2": 0.9, "y2": 0.3},
        ])
        graph = NeptuneGraph.__new__(NeptuneGraph)
        assert not graph.is_double_column(df)

    def test_double_column(self):
        df = pd.DataFrame([
            {"x1": 0.05, "y1": 0.0, "x2": 0.45, "y2": 0.1},
            {"x1": 0.05, "y1": 0.1, "x2": 0.45, "y2": 0.2},
            {"x1": 0.55, "y1": 0.0, "x2": 0.95, "y2": 0.1},
            {"x1": 0.55, "y1": 0.1, "x2": 0.95, "y2": 0.2},
        ])
        graph = NeptuneGraph.__new__(NeptuneGraph)
        assert graph.is_double_column(df)

    def test_reorder_double_column(self):
        df = pd.DataFrame([
            {"page": 1, "x1": 0.55, "y1": 0.0, "x2": 0.95, "y2": 0.1, "text": "right-1"},
            {"page": 1, "x1": 0.05, "y1": 0.0, "x2": 0.45, "y2": 0.1, "text": "left-1"},
            {"page": 1, "x1": 0.05, "y1": 0.1, "x2": 0.45, "y2": 0.2, "text": "left-2"},
            {"page": 1, "x1": 0.55, "y1": 0.1, "x2": 0.95, "y2": 0.2, "text": "right-2"},
        ])
        graph = NeptuneGraph.__new__(NeptuneGraph)
        reordered = graph.reorder_double_column(df)
        texts = reordered["text"].tolist()
        assert texts == ["left-1", "left-2", "right-1", "right-2"]
