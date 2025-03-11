from processors.opensearch_client import format_context_for_claude


class TestFormatContext:
    def test_formats_block_context(self):
        context_data = {
            "context_items": [
                {
                    "type": "Block",
                    "id": "block-1",
                    "text": "Transformers use self-attention.",
                    "block_type": "Paragraph",
                    "section_id": "section-1",
                    "section_title": "Introduction",
                    "paper_url": "https://example.com/paper.pdf",
                    "source": "primary",
                    "citations": [{"id": "b0", "title": "Attention Is All You Need"}],
                },
            ],
            "citations": [
                {"id": "b0", "title": "Attention Is All You Need", "authors": ["Vaswani"], "date": "2017"},
            ],
        }

        result = format_context_for_claude(context_data)
        assert "Introduction" in result
        assert "Transformers use self-attention." in result
        assert "[b0]" in result
        assert "Attention Is All You Need" in result

    def test_formats_cited_paper_tag(self):
        context_data = {
            "context_items": [
                {
                    "type": "Block",
                    "id": "cited-block-1",
                    "text": "From a cited paper.",
                    "block_type": "Paragraph",
                    "section_id": None,
                    "section_title": None,
                    "paper_url": "https://example.com/cited.pdf",
                    "source": "cited_paper",
                    "citations": [],
                },
            ],
            "citations": [],
        }

        result = format_context_for_claude(context_data)
        assert "(from cited paper)" in result

    def test_formats_section_context(self):
        context_data = {
            "context_items": [
                {
                    "type": "Section",
                    "id": "section-1",
                    "title": "Methodology",
                    "paper_url": "https://example.com/paper.pdf",
                    "blocks": [
                        {"id": "block-1", "text": "We used BERT.", "type": "Paragraph"},
                    ],
                    "citations": [],
                },
            ],
            "citations": [],
        }

        result = format_context_for_claude(context_data)
        assert "Methodology" in result
        assert "We used BERT." in result

    def test_formats_figure_context(self):
        context_data = {
            "context_items": [
                {
                    "type": "Figure",
                    "id": "figure-5",
                    "caption": "Fig 1: Model architecture",
                    "description": "A diagram showing transformer encoder-decoder layers with self-attention.",
                    "page": 3,
                    "s3_uri": "s3://bucket/figures/abc/figure_0.png",
                    "figure_type": "Figure",
                    "paper_url": "https://example.com/paper.pdf",
                },
            ],
            "citations": [],
        }

        result = format_context_for_claude(context_data)
        assert "Model architecture" in result
        assert "transformer encoder-decoder" in result
        assert "Page 3" in result

    def test_empty_context(self):
        result = format_context_for_claude({"context_items": [], "citations": []})
        assert "Relevant Research Paper Context" in result
