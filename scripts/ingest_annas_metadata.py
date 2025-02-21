"""
Ingest scientific paper metadata from Anna's Archive dumps into OpenSearch.

Only indexes records from scientific sources (Sci-Hub, LibGen scientific,
Crossref) that have DOIs and are PDFs. This filters the ~1.5TB full dump
down to ~50-80M scientific paper records.

Anna's Archive provides metadata exports as compressed JSONL files.
Download from: https://annas-archive.org/datasets

The dumps come in separate files per source:
  - annas_archive_meta__aac_scihub__*.jsonl.zst     (Sci-Hub — primary)
  - annas_archive_meta__aac_libgen_rs__*.jsonl.zst   (LibGen scientific)
  - annas_archive_meta__aac_crossref__*.jsonl.zst     (Crossref DOI metadata)

Usage:
    python scripts/ingest_annas_metadata.py /path/to/scihub_dump.jsonl
    python scripts/ingest_annas_metadata.py /path/to/dump.jsonl.zst
    python scripts/ingest_annas_metadata.py /path/to/dumps/ --batch-size 1000
"""
import argparse
import gzip
import json
import logging
import os

from config.settings import ANNAS_OPENSEARCH_ENDPOINT
from processors.annas_client import AnnasArchiveClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SCIENTIFIC_SOURCES = {"scihub", "libgen_rs", "crossref", "libgen_sci", "sci-hub"}


def safe_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def is_scientific_record(raw):
    source = raw.get("source", "").lower()
    if source and source not in SCIENTIFIC_SOURCES:
        return False

    ext = raw.get("extension", "").lower()
    if ext and ext != "pdf":
        return False

    if not raw.get("doi") and not raw.get("title"):
        return False

    topic = raw.get("topic", "").lower()
    non_scientific_topics = {"fiction", "comics", "magazine", "newspaper"}
    if topic in non_scientific_topics:
        return False

    return True


def parse_scientific_record(raw):
    return {
        "title": raw.get("title", ""),
        "authors": raw.get("author", ""),
        "doi": raw.get("doi", ""),
        "md5": raw.get("md5", ""),
        "year": safe_int(raw.get("year")),
        "language": raw.get("language", ""),
        "extension": raw.get("extension", "pdf"),
        "filesize": safe_int(raw.get("filesize")),
        "topic": raw.get("topic", ""),
        "description": raw.get("description", ""),
        "source": raw.get("source", ""),
        "ipfs_cid": raw.get("ipfs_cid", ""),
        "journal": raw.get("journal", ""),
        "publisher": raw.get("publisher", ""),
    }


def open_file(filepath):
    if filepath.endswith(".zst"):
        import zstandard
        dctx = zstandard.ZstdDecompressor()
        fh = open(filepath, "rb")
        return dctx.stream_reader(fh)
    elif filepath.endswith(".gz"):
        return gzip.open(filepath, "rt")
    else:
        return open(filepath, "r")


def ingest_file(filepath, client, batch_size=500):
    batch = []
    total = 0
    skipped = 0

    logger.info("Processing: %s", filepath)

    fh = open_file(filepath)
    try:
        for line in fh:
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            line = line.strip()
            if not line:
                continue

            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            if not is_scientific_record(raw):
                skipped += 1
                continue

            record = parse_scientific_record(raw)
            if not record["title"]:
                skipped += 1
                continue

            batch.append(record)

            if len(batch) >= batch_size:
                client.bulk_index(batch, batch_size=batch_size)
                total += len(batch)
                if total % 50000 == 0:
                    logger.info("Indexed: %d, skipped: %d", total, skipped)
                batch = []
    finally:
        fh.close()

    if batch:
        client.bulk_index(batch, batch_size=batch_size)
        total += len(batch)

    logger.info("File complete: %s — indexed: %d, skipped: %d", filepath, total, skipped)
    return total


def ingest_directory(dirpath, client, batch_size=500):
    total = 0
    for filename in sorted(os.listdir(dirpath)):
        if not any(filename.endswith(ext) for ext in (".jsonl", ".jsonl.zst", ".jsonl.gz")):
            continue

        scientific_prefixes = ("aac_scihub", "aac_libgen_rs", "aac_crossref")
        if not any(prefix in filename for prefix in scientific_prefixes):
            logger.info("Skipping non-scientific source: %s", filename)
            continue

        filepath = os.path.join(dirpath, filename)
        total += ingest_file(filepath, client, batch_size=batch_size)

    logger.info("Directory ingest complete. Total indexed: %d", total)
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest scientific paper metadata from Anna's Archive into OpenSearch"
    )
    parser.add_argument(
        "path",
        help="Path to JSONL file or directory of dump files",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    client = AnnasArchiveClient(ANNAS_OPENSEARCH_ENDPOINT)

    logger.info("Setting up Anna's Archive index")
    try:
        client.setup_index()
    except Exception:
        logger.info("Index already exists, continuing")

    if os.path.isdir(args.path):
        ingest_directory(args.path, client, batch_size=args.batch_size)
    else:
        ingest_file(args.path, client, batch_size=args.batch_size)
