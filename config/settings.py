import os

from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
BEDROCK_EMBEDDING_MODEL = os.getenv("BEDROCK_EMBEDDING_MODEL", "amazon.titan-embed-text-v1")
BEDROCK_LLM_MODEL = os.getenv("BEDROCK_LLM_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0")
OPENSEARCH_ENDPOINT = os.getenv("OPENSEARCH_ENDPOINT", "")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "papers")
OPENSEARCH_EMBEDDING_DIM = int(os.getenv("OPENSEARCH_EMBEDDING_DIM", "1536"))

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

GROBID_URL = os.getenv("GROBID_URL", "http://localhost:8070")
VILA_URL = os.getenv("VILA_URL", "http://127.0.0.1:8080")

SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
MAX_CITATION_DEPTH = int(os.getenv("MAX_CITATION_DEPTH", "1"))
MAX_CITED_PAPERS = int(os.getenv("MAX_CITED_PAPERS", "10"))
