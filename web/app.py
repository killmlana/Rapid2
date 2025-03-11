import logging
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config.settings import ANNAS_OPENSEARCH_ENDPOINT
from processors.annas_client import AnnasArchiveClient
from processors.opensearch_client import (
    setup_opensearch_index,
    index_papers_to_opensearch,
    process_rag_query,
)
from processors.neptune_client import NeptuneGraph
from processors.image_processor import ImageProcessor
from vila_parser import VilaClient
from grobid_client import GrobidClient
from processors.citation_crawler import CitationCrawler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Rapid2", version="1.0.0")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

jobs = {}
jobs_lock = threading.Lock()


class QueryRequest(BaseModel):
    query: str


class SearchRequest(BaseModel):
    topic: str
    max_papers: int = 5
    crawl_citations: bool = True
    year_from: int | None = None
    year_to: int | None = None


class IngestRequest(BaseModel):
    urls: list[str]
    crawl_citations: bool = True


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/api/query")
async def api_query(req: QueryRequest):
    result = process_rag_query(req.query)
    return {
        "query": result["query"],
        "response": result["response"],
        "citations": result["citations"],
    }


@app.post("/api/search")
async def api_search(req: SearchRequest):
    annas = AnnasArchiveClient(ANNAS_OPENSEARCH_ENDPOINT)
    filters = {}
    if req.year_from:
        filters["year_from"] = req.year_from
    if req.year_to:
        filters["year_to"] = req.year_to

    papers = annas.search_papers(req.topic, filters=filters or None, max_results=req.max_papers)
    results = []
    for p in papers:
        results.append({
            "title": p.get("title", ""),
            "authors": p.get("authors", ""),
            "year": p.get("year"),
            "doi": p.get("doi", ""),
            "journal": p.get("journal", ""),
            "source": p.get("source", ""),
            "score": p.get("_score", 0),
            "download_url": annas.resolve_download_url(p),
        })
    return {"papers": results, "total": len(results)}


def _run_ingest(job_id, urls, crawl_citations):
    try:
        with jobs_lock:
            jobs[job_id]["status"] = "processing"
            jobs[job_id]["total"] = len(urls)

        vila = VilaClient()
        grobid = GrobidClient()
        graph = NeptuneGraph()

        for i, url in enumerate(urls):
            with jobs_lock:
                jobs[job_id]["current"] = i + 1
                jobs[job_id]["current_url"] = url

            try:
                vila_df = vila.parse_pdf(url)
                xml_content = grobid.process_pdf(url)
                citations = grobid.parse_citations(xml_content)
                graph.store_paper(vila_df, citations, url)

                try:
                    img_proc = ImageProcessor()
                    figures = img_proc.process_paper_figures(url, vila_df)
                    if figures:
                        graph.store_figures(figures, url)
                except Exception:
                    logger.exception("Figure processing failed for: %s", url)

                if crawl_citations:
                    crawler = CitationCrawler(graph, grobid, vila)
                    crawler.crawl_paper_citations(url)

                with jobs_lock:
                    jobs[job_id]["completed"].append(url)
            except Exception as e:
                logger.exception("Failed to process: %s", url)
                with jobs_lock:
                    jobs[job_id]["failed"].append({"url": url, "error": str(e)})

        setup_opensearch_index()
        index_papers_to_opensearch()

        with jobs_lock:
            jobs[job_id]["status"] = "done"
    except Exception as e:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)


@app.post("/api/ingest")
async def api_ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "total": len(req.urls),
            "current": 0,
            "current_url": "",
            "completed": [],
            "failed": [],
        }
    background_tasks.add_task(_run_ingest, job_id, req.urls, req.crawl_citations)
    return {"job_id": job_id}


@app.post("/api/search-and-ingest")
async def api_search_and_ingest(req: SearchRequest, background_tasks: BackgroundTasks):
    annas = AnnasArchiveClient(ANNAS_OPENSEARCH_ENDPOINT)
    filters = {}
    if req.year_from:
        filters["year_from"] = req.year_from
    if req.year_to:
        filters["year_to"] = req.year_to

    papers = annas.search_papers(req.topic, filters=filters or None, max_results=req.max_papers)
    urls = [annas.resolve_download_url(p) for p in papers]
    urls = [u for u in urls if u]

    if not urls:
        return {"job_id": None, "papers": [], "message": "No downloadable papers found"}

    job_id = str(uuid.uuid4())[:8]
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "total": len(urls),
            "current": 0,
            "current_url": "",
            "completed": [],
            "failed": [],
        }
    background_tasks.add_task(_run_ingest, job_id, urls, req.crawl_citations)

    return {
        "job_id": job_id,
        "papers": [{"title": p.get("title", ""), "url": annas.resolve_download_url(p)} for p in papers],
    }


@app.get("/api/jobs/{job_id}")
async def api_job_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return {"error": "Job not found"}
    return job


@app.get("/api/health")
async def health():
    return {"status": "ok"}
