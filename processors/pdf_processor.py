import pandas as pd
import xml.etree.ElementTree as ET


class PDFProcessor:
    def parse_vila_csv(self, csv_path):
        df = pd.read_csv(csv_path).sort_values(["page", "y1"])
        document = {
            "metadata": {},
            "sections": [],
            "figures": [],
            "tables": [],
            "footnotes": [],
        }

        current_section = None

        for _, row in df.iterrows():
            if row["type"] == "Title":
                document["metadata"]["title"] = row["text"]
            elif row["type"] == "Author":
                document["metadata"]["authors"] = row["text"]
            elif row.get("block_type") == "Figure":
                document["figures"].append({
                    "caption": row["text"],
                    "page": row["page"],
                    "bbox": (row["x1"], row["y1"], row["x2"], row["y2"]),
                })
            elif row["type"] == "Section":
                current_section = self._handle_section_hierarchy(row["text"], document)
            elif row["type"] == "Footnote":
                document["footnotes"].append(row["text"])
            else:
                self._add_content(row, current_section)

        return document

    def _handle_section_hierarchy(self, section_text, document):
        first_token = str(section_text).split()[0] if " " in str(section_text) else str(section_text)

        if "." in first_token:
            parent_num = first_token.split(".")[0]
            parent = next((s for s in document["sections"] if s["num"] == parent_num), None)
            if not parent:
                parent = {"num": parent_num, "title": "", "subsections": [], "blocks": []}
                document["sections"].append(parent)

            subsection = {
                "num": first_token,
                "title": section_text,
                "blocks": [],
            }
            parent["subsections"].append(subsection)
            return subsection
        else:
            section = {
                "num": first_token,
                "title": section_text,
                "subsections": [],
                "blocks": [],
            }
            document["sections"].append(section)
            return section

    def _add_content(self, row, current_section):
        block = {
            "text": row["text"],
            "type": row["type"],
            "page": row["page"],
            "bbox": (row["x1"], row["y1"], row["x2"], row["y2"]),
        }
        if current_section:
            current_section["blocks"].append(block)
