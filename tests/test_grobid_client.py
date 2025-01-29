import pytest

from grobid_client import GrobidClient


SAMPLE_TEI_XML = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text>
    <body>
      <p>This references <ref type="bibr" target="#b0">Smith et al. (2020)</ref> and
      <ref type="bibr" target="#b1">Jones (2019)</ref>.</p>
    </body>
    <back>
      <listBibl>
        <biblStruct xml:id="b0">
          <analytic>
            <title>A Study on Transformers</title>
            <author><persName>John Smith</persName></author>
            <author><persName>Jane Doe</persName></author>
          </analytic>
          <monogr><imprint><date when="2020"/></imprint></monogr>
        </biblStruct>
        <biblStruct xml:id="b1">
          <analytic>
            <title>Deep Learning Advances</title>
            <author><persName>Bob Jones</persName></author>
          </analytic>
          <monogr><imprint><date when="2019"/></imprint></monogr>
        </biblStruct>
        <biblStruct xml:id="b2">
          <analytic>
            <title>No Date Paper</title>
          </analytic>
          <monogr><imprint/></monogr>
        </biblStruct>
      </listBibl>
    </back>
  </text>
</TEI>"""


class TestGrobidClient:
    def test_parse_citations_extracts_all(self):
        client = GrobidClient()
        citations = client.parse_citations(SAMPLE_TEI_XML)
        assert len(citations) == 3

    def test_parse_citations_fields(self):
        client = GrobidClient()
        citations = client.parse_citations(SAMPLE_TEI_XML)

        c0 = citations[0]
        assert c0["id"] == "b0"
        assert c0["title"] == "A Study on Transformers"
        assert c0["date"] == "2020"
        assert len(c0["authors"]) == 2
        assert "John Smith" in c0["authors"]

    def test_parse_citations_mentions(self):
        client = GrobidClient()
        citations = client.parse_citations(SAMPLE_TEI_XML)

        c0 = citations[0]
        assert len(c0["mentions"]) == 1
        assert "Smith et al. (2020)" in c0["mentions"][0]

        c1 = citations[1]
        assert len(c1["mentions"]) == 1

    def test_parse_citations_missing_date(self):
        client = GrobidClient()
        citations = client.parse_citations(SAMPLE_TEI_XML)

        c2 = citations[2]
        assert c2["date"] is None
        assert c2["title"] == "No Date Paper"
        assert c2["authors"] == []

    def test_parse_citations_empty_xml(self):
        xml = '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body/></text></TEI>'
        client = GrobidClient()
        citations = client.parse_citations(xml)
        assert citations == []
