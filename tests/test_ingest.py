from scripts.ingest_annas_metadata import is_scientific_record, parse_scientific_record


class TestIngestFiltering:
    def test_accepts_scihub_pdf(self):
        record = {"source": "scihub", "extension": "pdf", "doi": "10.1234/test", "title": "A Paper"}
        assert is_scientific_record(record)

    def test_accepts_libgen_rs_pdf(self):
        record = {"source": "libgen_rs", "extension": "pdf", "title": "Some Paper"}
        assert is_scientific_record(record)

    def test_accepts_crossref_pdf(self):
        record = {"source": "crossref", "extension": "pdf", "doi": "10.5678/abc", "title": "Another"}
        assert is_scientific_record(record)

    def test_rejects_fiction(self):
        record = {"source": "libgen_rs", "extension": "pdf", "topic": "fiction", "title": "Novel"}
        assert not is_scientific_record(record)

    def test_rejects_non_pdf(self):
        record = {"source": "scihub", "extension": "epub", "doi": "10.1234/test", "title": "A Paper"}
        assert not is_scientific_record(record)

    def test_rejects_non_scientific_source(self):
        record = {"source": "zlibrary", "extension": "pdf", "title": "A Book"}
        assert not is_scientific_record(record)

    def test_rejects_no_title_no_doi(self):
        record = {"source": "scihub", "extension": "pdf"}
        assert not is_scientific_record(record)

    def test_accepts_record_with_only_title(self):
        record = {"source": "scihub", "extension": "pdf", "title": "Title Only"}
        assert is_scientific_record(record)

    def test_accepts_no_source_with_doi(self):
        record = {"extension": "pdf", "doi": "10.1234/test", "title": "Paper"}
        assert is_scientific_record(record)

    def test_parse_scientific_record_fields(self):
        raw = {
            "title": "Attention Is All You Need",
            "author": "Vaswani et al.",
            "doi": "10.5555/3295222.3295349",
            "md5": "abc123",
            "year": "2017",
            "extension": "pdf",
            "source": "scihub",
            "journal": "NeurIPS",
            "publisher": "Curran Associates",
        }
        record = parse_scientific_record(raw)
        assert record["title"] == "Attention Is All You Need"
        assert record["doi"] == "10.5555/3295222.3295349"
        assert record["year"] == 2017
        assert record["journal"] == "NeurIPS"
        assert record["publisher"] == "Curran Associates"
