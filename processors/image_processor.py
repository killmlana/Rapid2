import base64
import hashlib
import io
import json
import logging
import tempfile

import boto3
import requests

from config.settings import AWS_REGION, BEDROCK_LLM_MODEL, S3_PAPERS_BUCKET

logger = logging.getLogger(__name__)


class ImageProcessor:
    def __init__(self):
        self.bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
        self.s3 = boto3.client("s3", region_name=AWS_REGION)
        self.bucket = S3_PAPERS_BUCKET

    def extract_figures_from_pdf(self, pdf_path_or_url, vila_df):
        try:
            from pdf2image import convert_from_path
        except ImportError:
            logger.warning("pdf2image not installed, skipping figure extraction")
            return []

        pdf_bytes = self._get_pdf_bytes(pdf_path_or_url)

        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()
            pages = convert_from_path(tmp.name, dpi=200)

        figure_rows = vila_df[
            vila_df["type"].isin(["Figure", "Table"])
            | (vila_df.get("block_type", "").isin(["Figure", "Table"]) if "block_type" in vila_df.columns else False)
        ]

        if figure_rows.empty and "block_type" in vila_df.columns:
            figure_rows = vila_df[vila_df["block_type"].isin(["Figure", "Table"])]

        figures = []
        for idx, row in figure_rows.iterrows():
            page_num = int(row["page"]) - 1
            if page_num < 0 or page_num >= len(pages):
                continue

            page_img = pages[page_num]
            pw, ph = page_img.size

            is_relative = all(0 <= row[c] <= 1.1 for c in ["x1", "y1", "x2", "y2"])
            if is_relative:
                x1 = int(row["x1"] * pw)
                y1 = int(row["y1"] * ph)
                x2 = int(row["x2"] * pw)
                y2 = int(row["y2"] * ph)
            else:
                x1 = int(row["x1"])
                y1 = int(row["y1"])
                x2 = int(row["x2"])
                y2 = int(row["y2"])

            padding = 10
            x1 = max(0, x1 - padding)
            y1 = max(0, y1 - padding)
            x2 = min(pw, x2 + padding)
            y2 = min(ph, y2 + padding)

            if x2 - x1 < 20 or y2 - y1 < 20:
                continue

            cropped = page_img.crop((x1, y1, x2, y2))

            buf = io.BytesIO()
            cropped.save(buf, format="PNG")
            image_bytes = buf.getvalue()

            figures.append({
                "image_bytes": image_bytes,
                "page": int(row["page"]),
                "bbox": [row["x1"], row["y1"], row["x2"], row["y2"]],
                "caption": str(row.get("text", "")),
                "type": str(row.get("type", row.get("block_type", "Figure"))),
                "idx": idx,
            })

        return figures

    def describe_image(self, image_bytes):
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        response = self.bedrock.invoke_model(
            modelId=BEDROCK_LLM_MODEL,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "temperature": 0,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this figure from a scientific paper in detail. "
                                "Include: what type of visualization it is (chart, diagram, "
                                "table, architecture, etc.), what data or concepts it shows, "
                                "key trends or values visible, and any labels or legends. "
                                "Be precise and factual."
                            ),
                        },
                    ],
                }],
            }),
        )

        result = json.loads(response["body"].read())
        return result["content"][0]["text"]

    def upload_to_s3(self, image_bytes, paper_url, figure_idx):
        url_hash = hashlib.md5(paper_url.encode()).hexdigest()[:12]
        key = f"figures/{url_hash}/figure_{figure_idx}.png"

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=image_bytes,
            ContentType="image/png",
        )

        return f"s3://{self.bucket}/{key}"

    def process_paper_figures(self, pdf_url, vila_df):
        figures = self.extract_figures_from_pdf(pdf_url, vila_df)

        if not figures:
            logger.info("No figures found in paper")
            return []

        logger.info("Found %d figures, processing...", len(figures))
        processed = []

        for i, fig in enumerate(figures):
            try:
                s3_uri = self.upload_to_s3(fig["image_bytes"], pdf_url, i)
                description = self.describe_image(fig["image_bytes"])

                processed.append({
                    "figure_id": f"figure-{fig['idx']}",
                    "page": fig["page"],
                    "bbox": fig["bbox"],
                    "caption": fig["caption"],
                    "description": description,
                    "s3_uri": s3_uri,
                    "type": fig["type"],
                })

                logger.info("Processed figure %d: %s", i, s3_uri)
            except Exception:
                logger.exception("Failed to process figure %d", i)
                continue

        return processed

    def _get_pdf_bytes(self, pdf_path_or_url):
        if pdf_path_or_url.startswith("http"):
            resp = requests.get(pdf_path_or_url, timeout=60)
            resp.raise_for_status()
            return resp.content
        with open(pdf_path_or_url, "rb") as f:
            return f.read()
