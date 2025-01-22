import pandas as pd
import requests

from config.settings import VILA_URL


class VilaClient:
    def __init__(self, service_url=None):
        self.service_url = service_url or VILA_URL

    def parse_pdf(self, pdf_url, relative_coordinates=True):
        resp = requests.get(
            f"{self.service_url}/parse/",
            params={
                "pdf_url": pdf_url,
                "relative_coordinates": str(relative_coordinates).lower(),
            },
            timeout=300,
        )
        resp.raise_for_status()
        return pd.read_csv(pd.io.common.StringIO(resp.text))
