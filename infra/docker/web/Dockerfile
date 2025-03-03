FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir "fastapi[standard]" uvicorn

COPY config/ /app/config/
COPY processors/ /app/processors/
COPY web/ /app/web/
COPY grobid_client.py vila_parser.py /app/

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
