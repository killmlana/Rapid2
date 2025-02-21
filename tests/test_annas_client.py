from processors.annas_client import AnnasArchiveClient


class TestAnnasArchiveClient:
    def test_resolve_download_url_doi(self):
        client = AnnasArchiveClient("dummy")
        paper = {"doi": "10.1234/test"}
        url = client.resolve_download_url(paper)
        assert "10.1234/test" in url

    def test_resolve_download_url_ipfs(self):
        client = AnnasArchiveClient("dummy")
        paper = {"ipfs_cid": "QmTestHash123"}
        url = client.resolve_download_url(paper)
        assert "QmTestHash123" in url

    def test_resolve_download_url_md5(self):
        client = AnnasArchiveClient("dummy")
        paper = {"md5": "abc123def456"}
        url = client.resolve_download_url(paper)
        assert "abc123def456" in url

    def test_resolve_download_url_none(self):
        client = AnnasArchiveClient("dummy")
        paper = {}
        assert client.resolve_download_url(paper) is None

    def test_resolve_download_url_doi_takes_priority(self):
        client = AnnasArchiveClient("dummy")
        paper = {
            "doi": "10.1234/test",
            "md5": "abc123",
            "ipfs_cid": "QmHash",
        }
        url = client.resolve_download_url(paper)
        assert "10.1234/test" in url
