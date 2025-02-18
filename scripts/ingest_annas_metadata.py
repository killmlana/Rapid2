"""
Ingest Anna's Archive metadata dumps into OpenSearch.

Anna's Archive provides metadata exports as compressed JSON/CSV files.
Download from: https://annas-archive.org/datasets

Usage:
    python scripts/ingest_annas_metadata.py /path/to/metadata_dump.jsonl
    python scripts/ingest_annas_metadata.py /path/to/dump.jsonl --batch-size 1000
"""
import argparse
import json
import logging
import sys

from config.settings import ANNAS_OPENSEARCH_ENDPOINT
from processors.annas_client import AnnasArchiveClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_metadata_line(line):
    raw = json.loads(line)

    return {
        "title": raw.get("title", ""),
        "authors": raw.get("author", ""),
        "doi": raw.get("doi", ""),
        "isbn": raw.get("isbn", ""),
        "md5": raw.get("md5", ""),
        "year": safe_int(raw.get("year")),
        "language": raw.get("language", ""),
        "extension": raw.get("extension", ""),
        "filesize": safe_int(raw.get("filesize")),
        "topic": raw.get("topic", ""),
        "description": raw.get("description", ""),
        "source": raw.get("source", ""),
        "ipfs_cid": raw.get("ipfs_cid", ""),
    }


def safe_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def ingest_file(filepath, batch_size=500):
    client = AnnasArchiveClient(ANNAS_OPENSEARCH_ENDPOINT)

    logger.info("Setting up Anna's Archive index")
    try:
        client.setup_index()
    except Exception:
        logger.info("Index already exists, continuing")

    batch = []
    total = 0

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                record = parse_metadata_line(line)
            except (json.JSONDecodeError, KeyError):
                continue

            if not record["title"]:
                continue

            batch.append(record)

            if len(batch) >= batch_size:
                client.bulk_index(batch, batch_size=batch_size)
                total += len(batch)
                logger.info("Total indexed: %d", total)
                batch = []

    if batch:
        client.bulk_index(batch, batch_size=batch_size)
        total += len(batch)

    logger.info("Ingest complete. Total records: %d", total)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Anna's Archive metadata into OpenSearch")
    parser.add_argument("filepath", help="Path to JSONL metadata dump")
    parser.add_argument("--batch-size", type=int, default=500, help="Bulk index batch size")
    args = parser.parse_args()

    ingest_file(args.filepath, batch_size=args.batch_size)
