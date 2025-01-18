import pandas as pd

def parse_vila_csv(csv_path):
    df = pd.read_csv(csv_path)
    df = df.sort_values(["page", "y1"])
    
    document = {
        "sections": [],
        "figures": [],
        "footnotes": []
    }
    current_section = None
    current_subsection = None
    
    for _, row in df.iterrows():
        # Handle section hierarchy (e.g., "2.1 Structured Content Extraction")
        if row["type"] == "Section":
            if "." in row["text"]:  # Subsection detection
                section_parts = row["text"].split(".")
                parent_section = section_parts[0].strip()
                subsection = ".".join(section_parts[:2]).strip()
                
                # Find or create parent section
                parent = next((s for s in document["sections"] if s["title"] == parent_section), None)
                if not parent:
                    parent = {"title": parent_section, "subsections": []}
                    document["sections"].append(parent)
                
                # Add subsection
                current_subsection = {
                    "title": subsection,
                    "blocks": [],
                    "parent": parent_section
                }
                parent["subsections"].append(current_subsection)
            else:
                current_section = {
                    "title": row["text"].strip(),
                    "blocks": [],
                    "subsections": []
                }
                document["sections"].append(current_section)
        
        # Handle figures and captions
        elif row["block_type"] == "Figure":
            document["figures"].append({
                "caption": row["text"],
                "page": row["page"],
                "bbox": (row["x1"], row["y1"], row["x2"], row["y2"])
            })
        
        # Handle footnotes
        elif row["type"] == "Footnote":
            document["footnotes"].append({
                "text": row["text"],
                "page": row["page"],
                "block_id": row["block_id"]
            })
        
        # Add content to current section/subsection
        else:
            target = current_subsection if current_subsection else current_section
            if target:
                target["blocks"].append({
                    "text": row["text"],
                    "type": row["type"],
                    "page": row["page"],
                    "bbox": (row["x1"], row["y1"], row["x2"], row["y2"]),
                    "block_id": row["block_id"]
                })
    
    return document