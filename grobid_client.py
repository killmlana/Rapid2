import tempfile
import xml.etree.ElementTree as ET

import requests

from config.settings import GROBID_URL


class GrobidClient:
    def __init__(self, grobid_url=None):
        self.grobid_url = grobid_url or GROBID_URL

    def process_pdf(self, pdf_path_or_url):
        if pdf_path_or_url.startswith("http"):
            resp = requests.get(pdf_path_or_url, timeout=60)
            resp.raise_for_status()
            pdf_bytes = resp.content
        else:
            with open(pdf_path_or_url, "rb") as f:
                pdf_bytes = f.read()

        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()
            with open(tmp.name, "rb") as fh:
                response = requests.post(
                    f"{self.grobid_url}/api/processFulltextDocument",
                    files={"input": fh},
                    data={"consolidateCitations": "1"},
                    timeout=120,
                )
        response.raise_for_status()
        return response.text

    def parse_citations(self, xml_content):
        ns = {"tei": "http://www.tei-c.org/ns/1.0"}
        root = ET.fromstring(xml_content)

        citations = []
        for bibl in root.findall(".//tei:biblStruct", ns):
            bibl_id = bibl.attrib.get("{http://www.w3.org/XML/1998/namespace}id")

            date_el = bibl.find(".//tei:date", ns)
            date = date_el.attrib.get("when") if date_el is not None else None

            title_el = bibl.find(".//tei:title", ns)
            title = title_el.text if title_el is not None else None

            authors = []
            for pers in bibl.findall(".//tei:author/tei:persName", ns):
                name = " ".join(pers.itertext()).strip()
                if name:
                    authors.append(name)

            citations.append({
                "id": bibl_id,
                "authors": authors,
                "title": title,
                "date": date,
                "mentions": [],
            })

        for ref in root.findall('.//tei:ref[@type="bibr"]', ns):
            target = ref.attrib.get("target")
            if target is None:
                continue
            target = target.replace("#", "")
            text = "".join(ref.itertext()).strip()
            for c in citations:
                if c["id"] == target:
                    c["mentions"].append(text)

        return citations
