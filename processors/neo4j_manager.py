from collections import defaultdict

import pandas as pd
from neo4j import GraphDatabase

from config.settings import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD


class Neo4jGraph:
    def __init__(self, uri=None, user=None, password=None):
        self.driver = GraphDatabase.driver(
            uri or NEO4J_URI,
            auth=(user or NEO4J_USERNAME, password or NEO4J_PASSWORD),
        )

    def close(self):
        self.driver.close()

    def create_schema(self):
        with self.driver.session() as session:
            for label, prop in [("Paper", "url"), ("Citation", "id"), ("Section", "id")]:
                session.run(
                    f"CREATE CONSTRAINT {label.lower()}_{prop}_unique IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
                )

    def is_double_column(self, df):
        x_mid = (df["x1"].min() + df["x2"].max()) / 2
        left_count = ((df["x1"] + df["x2"]) / 2 < x_mid).sum()
        right_count = ((df["x1"] + df["x2"]) / 2 >= x_mid).sum()
        return min(left_count, right_count) > len(df) * 0.2

    def reorder_double_column(self, df):
        pages = defaultdict(list)
        for i, row in df.iterrows():
            pages[row["page"]].append((i, row))

        reordered_indices = []
        for page_num in sorted(pages.keys()):
            page_rows = pages[page_num]
            x_max = max([row["x2"] for _, row in page_rows])
            column_boundary = x_max / 2

            left_column = []
            right_column = []
            for idx, row in page_rows:
                center_x = (row["x1"] + row["x2"]) / 2
                if center_x < column_boundary:
                    left_column.append((idx, row))
                else:
                    right_column.append((idx, row))

            left_column.sort(key=lambda x: x[1]["y1"])
            right_column.sort(key=lambda x: x[1]["y1"])
            reordered_indices.extend([idx for idx, _ in left_column])
            reordered_indices.extend([idx for idx, _ in right_column])

        return df.loc[reordered_indices].reset_index(drop=True)

    def store_paper(self, vila_df, citations, pdf_url):
        vila_df = vila_df.sort_values(by=["page", "y1"]).reset_index(drop=True)

        if self.is_double_column(vila_df):
            vila_df = self.reorder_double_column(vila_df)

        with self.driver.session() as session:
            session.run("MERGE (p:Paper {url: $url})", url=pdf_url)

        sections = {}
        with self.driver.session() as session:
            if any(row["type"] == "Abstract" for _, row in vila_df.iterrows()):
                session.run(
                    "MATCH (p:Paper {url: $url}) "
                    "MERGE (s:Section {id: 'section-abstract'}) "
                    "SET s.title = 'Abstract', s.level = 1 "
                    "WITH s, p MERGE (s)-[:PART_OF]->(p)",
                    url=pdf_url,
                )
                sections["section-abstract"] = {"level": 1, "title": "Abstract"}

            for i, row in vila_df[vila_df["type"] == "Section"].iterrows():
                section_id = f"section-{i}"
                title = row["text"]
                level = 1
                if title and " " in str(title) and "." in str(title).split()[0]:
                    level = str(title).split()[0].count(".") + 1

                session.run(
                    "MATCH (p:Paper {url: $url}) "
                    "MERGE (s:Section {id: $id}) "
                    "SET s.title = $title, s.level = $level "
                    "WITH s, p MERGE (s)-[:PART_OF]->(p)",
                    url=pdf_url, id=section_id, title=title, level=level,
                )
                sections[section_id] = {"level": level, "title": title}

        with self.driver.session() as session:
            session.run(
                "MATCH (p:Paper {url: $url}) "
                "MERGE (s:Section {id: 'section-unassigned'}) "
                "SET s.title = 'Unassigned Content', s.level = 1 "
                "WITH s, p MERGE (s)-[:PART_OF]->(p)",
                url=pdf_url,
            )
            sections["section-unassigned"] = {"level": 1, "title": "Unassigned Content"}

            for child_id, child_info in sections.items():
                if child_info["level"] <= 1:
                    continue
                child_number = str(child_info["title"]).split()[0] if " " in str(child_info["title"]) else ""
                if "." in child_number:
                    parent_prefix = ".".join(child_number.split(".")[:-1])
                    for parent_id, parent_info in sections.items():
                        if parent_info["level"] == child_info["level"] - 1:
                            parent_number = str(parent_info["title"]).split()[0] if " " in str(parent_info["title"]) else ""
                            if parent_number == parent_prefix:
                                session.run(
                                    "MATCH (parent:Section {id: $parent_id}) "
                                    "MATCH (child:Section {id: $child_id}) "
                                    "MERGE (child)-[:SUBSECTION_OF]->(parent)",
                                    parent_id=parent_id, child_id=child_id,
                                )
                                break

        with self.driver.session() as session:
            for citation in citations:
                if not citation.get("id"):
                    continue
                session.run(
                    "MERGE (c:Citation {id: $id}) "
                    "SET c.title = $title, c.authors = $authors, c.date = $date",
                    id=citation["id"],
                    title=citation.get("title", ""),
                    authors=citation.get("authors", []),
                    date=citation.get("date", ""),
                )

        current_section_id = "section-unassigned"
        with self.driver.session() as session:
            for i, row in vila_df.iterrows():
                if row["type"] == "Section":
                    current_section_id = f"section-{i}"
                    continue
                elif row["type"] == "Abstract":
                    current_section_id = "section-abstract"

                block_id = f"block-{i}"
                bbox = [
                    float(row["x1"]) if not pd.isna(row["x1"]) else 0.0,
                    float(row["y1"]) if not pd.isna(row["y1"]) else 0.0,
                    float(row["x2"]) if not pd.isna(row["x2"]) else 0.0,
                    float(row["y2"]) if not pd.isna(row["y2"]) else 0.0,
                ]

                session.run(
                    "CREATE (b:Block {id: $id, text: $text, type: $type, page: $page, bbox: $bbox})",
                    id=block_id,
                    text=str(row["text"]) if not pd.isna(row["text"]) else "",
                    type=row["type"],
                    page=int(row["page"]) if not pd.isna(row["page"]) else 0,
                    bbox=bbox,
                )

                session.run(
                    "MATCH (b:Block {id: $block_id}) "
                    "MATCH (s:Section {id: $section_id}) "
                    "CREATE (b)-[:CONTAINED_IN]->(s)",
                    block_id=block_id, section_id=current_section_id,
                )

                for citation in citations:
                    if not citation.get("id") or "mentions" not in citation:
                        continue
                    for mention in citation.get("mentions", []):
                        if mention and mention in str(row["text"]):
                            session.run(
                                "MATCH (b:Block {id: $block_id}) "
                                "MATCH (c:Citation {id: $cit_id}) "
                                "CREATE (b)-[:CITES]->(c)",
                                block_id=block_id, cit_id=citation["id"],
                            )

    def get_full_context(self, block_id):
        with self.driver.session() as session:
            result = session.run(
                "MATCH (b:Block {id: $block_id})-[:CONTAINED_IN]->(s:Section)-[:PART_OF]->(p:Paper) "
                "OPTIONAL MATCH (b)-[:CITES]->(c:Citation) "
                "RETURN b, s, p, COLLECT(DISTINCT c) AS citations",
                block_id=block_id,
            ).single()

            if not result:
                return None

            return {
                "block": dict(result["b"]),
                "section": dict(result["s"]),
                "paper": dict(result["p"]),
                "citations": [dict(c) for c in result["citations"]],
            }

    def get_paper_citations(self, paper_url):
        with self.driver.session() as session:
            results = session.run(
                "MATCH (b:Block)-[:CONTAINED_IN]->(s:Section)-[:PART_OF]->(p:Paper {url: $url}) "
                "MATCH (b)-[:CITES]->(c:Citation) "
                "RETURN DISTINCT c.id AS id, c.title AS title, c.authors AS authors, c.date AS date",
                url=paper_url,
            ).data()
            return results

    def store_cited_paper_context(self, parent_paper_url, cited_paper_url, relevant_blocks):
        with self.driver.session() as session:
            session.run("MERGE (p:Paper {url: $url})", url=cited_paper_url)
            session.run(
                "MATCH (parent:Paper {url: $parent_url}) "
                "MATCH (cited:Paper {url: $cited_url}) "
                "MERGE (parent)-[:REFERENCES]->(cited)",
                parent_url=parent_paper_url, cited_url=cited_paper_url,
            )

            for block in relevant_blocks:
                block_id = f"cited-block-{hash(block['text'][:50])}"
                session.run(
                    "MERGE (b:Block {id: $id}) "
                    "SET b.text = $text, b.type = $type, b.source = 'cited_paper' "
                    "WITH b "
                    "MATCH (p:Paper {url: $url}) "
                    "MERGE (b)-[:CONTAINED_IN_CITED]->(p)",
                    id=block_id, text=block["text"], type=block.get("type", "Paragraph"),
                    url=cited_paper_url,
                )
