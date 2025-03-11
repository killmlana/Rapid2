import json
import logging
from collections import defaultdict

import boto3
import pandas as pd
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

import requests as http_requests

from config.settings import AWS_REGION, NEPTUNE_ENDPOINT, NEPTUNE_PORT

logger = logging.getLogger(__name__)


class NeptuneGraph:
    def __init__(self, endpoint=None, port=None):
        self.endpoint = endpoint or NEPTUNE_ENDPOINT
        self.port = port or NEPTUNE_PORT
        self.base_url = f"https://{self.endpoint}:{self.port}"
        self.session = boto3.Session(region_name=AWS_REGION)

    def _signed_request(self, method, path, body=None):
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}

        req = AWSRequest(method=method, url=url, data=body, headers=headers)
        SigV4Auth(self.session.get_credentials(), "neptune-db", AWS_REGION).add_auth(req)

        resp = http_requests.request(
            method=method,
            url=url,
            headers=dict(req.headers),
            data=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _query(self, cypher, parameters=None):
        body = json.dumps({
            "query": cypher,
            "parameters": parameters or {},
        })
        return self._signed_request("POST", "/opencypher", body)

    def create_schema(self):
        pass

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

        self._query(
            "MERGE (p:Paper {url: $url})",
            {"url": pdf_url},
        )

        sections = {}
        if any(row["type"] == "Abstract" for _, row in vila_df.iterrows()):
            self._query(
                "MATCH (p:Paper {url: $url}) "
                "MERGE (s:Section {id: 'section-abstract'}) "
                "SET s.title = 'Abstract', s.level = 1 "
                "WITH s, p "
                "MERGE (s)-[:PART_OF]->(p)",
                {"url": pdf_url},
            )
            sections["section-abstract"] = {"level": 1, "title": "Abstract"}

        for i, row in vila_df[vila_df["type"] == "Section"].iterrows():
            section_id = f"section-{i}"
            title = row["text"]
            level = 1
            if title and " " in str(title) and "." in str(title).split()[0]:
                level = str(title).split()[0].count(".") + 1

            self._query(
                "MATCH (p:Paper {url: $url}) "
                "MERGE (s:Section {id: $id}) "
                "SET s.title = $title, s.level = $level "
                "WITH s, p "
                "MERGE (s)-[:PART_OF]->(p)",
                {"url": pdf_url, "id": section_id, "title": title, "level": level},
            )
            sections[section_id] = {"level": level, "title": title}

        self._query(
            "MATCH (p:Paper {url: $url}) "
            "MERGE (s:Section {id: 'section-unassigned'}) "
            "SET s.title = 'Unassigned Content', s.level = 1 "
            "WITH s, p "
            "MERGE (s)-[:PART_OF]->(p)",
            {"url": pdf_url},
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
                            self._query(
                                "MATCH (parent:Section {id: $parent_id}) "
                                "MATCH (child:Section {id: $child_id}) "
                                "MERGE (child)-[:SUBSECTION_OF]->(parent)",
                                {"parent_id": parent_id, "child_id": child_id},
                            )
                            break

        for citation in citations:
            if not citation.get("id"):
                continue
            self._query(
                "MERGE (c:Citation {id: $id}) "
                "SET c.title = $title, c.authors = $authors, c.date = $date",
                {
                    "id": citation["id"],
                    "title": citation.get("title", ""),
                    "authors": citation.get("authors", []),
                    "date": citation.get("date", ""),
                },
            )

        current_section_id = "section-unassigned"
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

            self._query(
                "CREATE (b:Block {"
                "id: $id, text: $text, type: $type, page: $page, "
                "bbox_x1: $bx1, bbox_y1: $by1, bbox_x2: $bx2, bbox_y2: $by2"
                "})",
                {
                    "id": block_id,
                    "text": str(row["text"]) if not pd.isna(row["text"]) else "",
                    "type": row["type"],
                    "page": int(row["page"]) if not pd.isna(row["page"]) else 0,
                    "bx1": bbox[0], "by1": bbox[1], "bx2": bbox[2], "by2": bbox[3],
                },
            )

            self._query(
                "MATCH (b:Block {id: $block_id}) "
                "MATCH (s:Section {id: $section_id}) "
                "CREATE (b)-[:CONTAINED_IN]->(s)",
                {"block_id": block_id, "section_id": current_section_id},
            )

            for citation in citations:
                if not citation.get("id") or "mentions" not in citation:
                    continue
                for mention in citation.get("mentions", []):
                    if mention and mention in str(row["text"]):
                        self._query(
                            "MATCH (b:Block {id: $block_id}) "
                            "MATCH (c:Citation {id: $cit_id}) "
                            "CREATE (b)-[:CITES]->(c)",
                            {"block_id": block_id, "cit_id": citation["id"]},
                        )

    def get_full_context(self, block_id):
        result = self._query(
            "MATCH (b:Block {id: $block_id})-[:CONTAINED_IN]->(s:Section)-[:PART_OF]->(p:Paper) "
            "OPTIONAL MATCH (b)-[:CITES]->(c:Citation) "
            "RETURN b.id AS block_id, b.text AS block_text, b.type AS block_type, "
            "s.id AS section_id, s.title AS section_title, p.url AS paper_url, "
            "COLLECT(DISTINCT {id: c.id, title: c.title, authors: c.authors, date: c.date}) AS citations",
            {"block_id": block_id},
        )

        rows = result.get("results", [])
        if not rows:
            return None

        r = rows[0]
        return {
            "block": {"id": r["block_id"], "text": r["block_text"], "type": r["block_type"]},
            "section": {"id": r["section_id"], "title": r["section_title"]},
            "paper": {"url": r["paper_url"]},
            "citations": [c for c in r.get("citations", []) if c.get("id")],
        }

    def get_paper_citations(self, paper_url):
        result = self._query(
            "MATCH (b:Block)-[:CONTAINED_IN]->(s:Section)-[:PART_OF]->(p:Paper {url: $url}) "
            "MATCH (b)-[:CITES]->(c:Citation) "
            "RETURN DISTINCT c.id AS id, c.title AS title, c.authors AS authors, c.date AS date",
            {"url": paper_url},
        )
        return result.get("results", [])

    def store_cited_paper_context(self, parent_paper_url, cited_paper_url, relevant_blocks):
        self._query(
            "MERGE (p:Paper {url: $url})",
            {"url": cited_paper_url},
        )
        self._query(
            "MATCH (parent:Paper {url: $parent_url}) "
            "MATCH (cited:Paper {url: $cited_url}) "
            "MERGE (parent)-[:REFERENCES]->(cited)",
            {"parent_url": parent_paper_url, "cited_url": cited_paper_url},
        )

        for block in relevant_blocks:
            block_id = f"cited-block-{hash(block['text'][:50])}"
            self._query(
                "MERGE (b:Block {id: $id}) "
                "SET b.text = $text, b.type = $type, b.source = 'cited_paper' "
                "WITH b "
                "MATCH (p:Paper {url: $url}) "
                "MERGE (b)-[:CONTAINED_IN_CITED]->(p)",
                {
                    "id": block_id,
                    "text": block["text"],
                    "type": block.get("type", "Paragraph"),
                    "url": cited_paper_url,
                },
            )

    def store_figures(self, figures, pdf_url, current_section_id="section-unassigned"):
        for fig in figures:
            self._query(
                "CREATE (f:Figure {"
                "id: $id, caption: $caption, description: $description, "
                "page: $page, s3_uri: $s3_uri, figure_type: $figure_type"
                "})",
                {
                    "id": fig["figure_id"],
                    "caption": fig.get("caption", ""),
                    "description": fig["description"],
                    "page": fig["page"],
                    "s3_uri": fig["s3_uri"],
                    "figure_type": fig.get("type", "Figure"),
                },
            )
            self._query(
                "MATCH (f:Figure {id: $fig_id}) "
                "MATCH (p:Paper {url: $url}) "
                "CREATE (f)-[:PART_OF]->(p)",
                {"fig_id": fig["figure_id"], "url": pdf_url},
            )

    def close(self):
        pass
