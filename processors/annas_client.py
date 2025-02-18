import json
import logging

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import requests as http_requests

from config.settings import AWS_REGION

logger = logging.getLogger(__name__)

ANNAS_INDEX = "annas-metadata"


class AnnasArchiveClient:
    """Search Anna's Archive metadata indexed in OpenSearch for paper discovery."""

    def __init__(self, opensearch_endpoint):
        self.endpoint = opensearch_endpoint
        self.base_url = f"https://{self.endpoint}"
        self.session = boto3.Session(region_name=AWS_REGION)

    def _signed_request(self, method, path, body=None):
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}

        req = AWSRequest(method=method, url=url, data=body, headers=headers)
        SigV4Auth(self.session.get_credentials(), "es", AWS_REGION).add_auth(req)

        resp = http_requests.request(
            method=method,
            url=url,
            headers=dict(req.headers),
            data=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def setup_index(self):
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text", "analyzer": "english"},
                    "authors": {"type": "text"},
                    "doi": {"type": "keyword"},
                    "isbn": {"type": "keyword"},
                    "md5": {"type": "keyword"},
                    "year": {"type": "integer"},
                    "language": {"type": "keyword"},
                    "extension": {"type": "keyword"},
                    "filesize": {"type": "long"},
                    "topic": {"type": "text"},
                    "description": {"type": "text", "analyzer": "english"},
                    "source": {"type": "keyword"},
                    "download_url": {"type": "keyword"},
                    "ipfs_cid": {"type": "keyword"},
                },
            },
            "settings": {
                "number_of_shards": 3,
                "number_of_replicas": 1,
            },
        }
        self._signed_request("PUT", f"/{ANNAS_INDEX}", json.dumps(mapping))
        logger.info("Created Anna's Archive metadata index")

    def index_record(self, record):
        self._signed_request(
            "POST",
            f"/{ANNAS_INDEX}/_doc",
            json.dumps(record),
        )

    def bulk_index(self, records, batch_size=500):
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            body_lines = []
            for record in batch:
                body_lines.append(json.dumps({"index": {"_index": ANNAS_INDEX}}))
                body_lines.append(json.dumps(record))
            body = "\n".join(body_lines) + "\n"

            self._signed_request("POST", "/_bulk", body)
            logger.info("Indexed batch %d-%d", i, min(i + batch_size, len(records)))

    def search_papers(self, query, filters=None, max_results=20):
        must_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "authors^2", "description", "topic"],
                    "type": "best_fields",
                }
            }
        ]

        filter_clauses = [
            {"term": {"extension": "pdf"}},
        ]

        if filters:
            if filters.get("year_from"):
                filter_clauses.append({"range": {"year": {"gte": filters["year_from"]}}})
            if filters.get("year_to"):
                filter_clauses.append({"range": {"year": {"lte": filters["year_to"]}}})
            if filters.get("language"):
                filter_clauses.append({"term": {"language": filters["language"]}})

        search_body = {
            "size": max_results,
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses,
                }
            },
            "_source": [
                "title", "authors", "doi", "md5", "year",
                "extension", "source", "download_url", "ipfs_cid",
            ],
        }

        result = self._signed_request(
            "POST",
            f"/{ANNAS_INDEX}/_search",
            json.dumps(search_body),
        )

        papers = []
        for hit in result.get("hits", {}).get("hits", []):
            src = hit["_source"]
            src["_score"] = hit["_score"]
            papers.append(src)

        return papers

    def resolve_download_url(self, paper):
        if paper.get("download_url"):
            return paper["download_url"]

        if paper.get("doi"):
            return f"https://sci-hub.se/{paper['doi']}"

        if paper.get("ipfs_cid"):
            return f"https://ipfs.io/ipfs/{paper['ipfs_cid']}"

        if paper.get("md5"):
            return f"https://library.lol/main/{paper['md5']}"

        return None
