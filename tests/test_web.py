import pytest
from fastapi.testclient import TestClient

from web.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestWebApp:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_index_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Rapid2" in resp.text

    def test_query_requires_body(self, client):
        resp = client.post("/api/query", json={})
        assert resp.status_code == 422

    def test_search_requires_topic(self, client):
        resp = client.post("/api/search", json={})
        assert resp.status_code == 422

    def test_ingest_requires_urls(self, client):
        resp = client.post("/api/ingest", json={})
        assert resp.status_code == 422

    def test_job_not_found(self, client):
        resp = client.get("/api/jobs/nonexistent")
        assert resp.status_code == 200
        assert resp.json()["error"] == "Job not found"
