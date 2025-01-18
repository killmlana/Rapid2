import pandas as pd
import xml.etree.ElementTree as ET
from grobid_client.grobid_client import GrobidClient
from fuzzywuzzy import fuzz

class PDFProcessor:
    def __init__(self, grobid_config="./config/grobid.json"):
        self.grobid_client = GrobidClient(config_path=grobid_config)
        
    def parse_vila_csv(self, csv_path):
        """Parse VILA CSV into hierarchical document structure"""
        df = pd.read_csv(csv_path).sort_values(["page", "y1"])
        document = {
            "metadata": {},
            "sections": [],
            "figures": [],
            "tables": [],
            "footnotes": []
        }
        
        current_section = None
        current_subsection = None
        
        for _, row in df.iterrows():
            if row["type"] == "Title":
                document["metadata"]["title"] = row["text"]
            elif row["type"] == "Author":
                document["metadata"]["authors"] = row["text"]
            elif row["block_type"] == "Figure":
                document["figures"].append({
                    "caption": row["text"],
                    "page": row["page"],
                    "bbox": (row["x1"], row["y1"], row["x2"], row["y2"])
                })
            elif row["type"] == "Section":
                current_section = self._handle_section_hierarchy(row["text"], document)
            elif row["type"] == "Footnote":
                document["footnotes"].append(row["text"])
            else:
                self._add_content(row, current_section, document)
        
        return document

    def _handle_section_hierarchy(self, section_text, document):
        """Handle section/subsection numbering (e.g., '2.1 Methodology')"""
        parts = section_text.split(".")
        parent_num = parts[0].strip()
        
        # Find existing parent section
        parent = next((s for s in document["sections"] if s["num"] == parent_num), None)
        
        if len(parts) > 1:  # Subsection
            if not parent:
                parent = {"num": parent_num, "title": "", "subsections": []}
                document["sections"].append(parent)
            
            subsection = {
                "num": ".".join(parts[:2]),
                "title": section_text,
                "blocks": []
            }
            parent["subsections"].append(subsection)
            return subsection
        else:  # Top-level section
            section = {
                "num": parent_num,
                "title": section_text,
                "subsections": [],
                "blocks": []
            }
            document["sections"].append(section)
            return section

    def _add_content(self, row, current_section, document):
        """Add content blocks to appropriate section"""
        block = {
            "text": row["text"],
            "type": row["type"],
            "page": row["page"],
            "bbox": (row["x1"], row["y1"], row["x2"], row["y2"]),
            "citations": []
        }
        
        if current_section:
            if "subsections" in current_section:  # Parent section
                current_section["blocks"].append(block)
            else:  # Subsection
                current_section["blocks"].append(block)

    def extract_citations(self, pdf_path):
        """Process PDF with GROBID and extract citations"""
        xml_path = self.grobid_client.process(
            "processFulltextDocument", 
            pdf_path, 
            output="./data/grobid_output",
            consolidate_citations=True
        )
        return self._parse_grobid_xml(xml_path)

    def _parse_grobid_xml(self, xml_path):
        """Parse GROBID XML output"""
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {"tei": "http://www.tei-c.org/ns/1.0"}
        
        citations = []
        for ref in root.findall(".//tei:biblStruct", ns):
            citation = {
                "id": ref.attrib.get("xml:id"),
                "authors": [a.text for a in ref.findall(".//tei:author/tei:persName/tei:forename", ns)],
                "title": ref.find(".//tei:title", ns).text
            }
            citations.append(citation)
        
        return citations

    def link_citations(self, document, citations):
        """Link GROBID citations to document blocks"""
        for citation in citations:
            for section in document["sections"]:
                self._match_citation_to_blocks(citation, section, "title")
                for subsection in section.get("subsections", []):
                    self._match_citation_to_blocks(citation, subsection, "title")
        
        for fig in document["figures"]:
            if any(c["title"] in fig["caption"] for c in citations):
                fig["citations"] = [c["id"] for c in citations if c["title"] in fig["caption"]]
        
        return document

    def _match_citation_to_blocks(self, citation, section, match_field):
        """Fuzzy match citations to section blocks"""
        for block in section["blocks"]:
            if fuzz.partial_ratio(citation[match_field], block["text"]) > 75:
                block["citations"].append(citation["id"])