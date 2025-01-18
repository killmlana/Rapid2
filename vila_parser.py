import requests
import pandas as pd

class VilaClient:
    def __init__(self, service_url="http://127.0.0.1:8080"):
        self.service_url = service_url
    
    def parse_pdf(self, pdf_url, relative_coordinates=True):
        params = {
            "pdf_url": pdf_url,
            "relative_coordinates": str(relative_coordinates).lower()
        }
        return pd.read_csv(f"http://127.0.0.1:8080/parse/?pdf_url={pdf_url}&relative_coordinates={relative_coordinates}")