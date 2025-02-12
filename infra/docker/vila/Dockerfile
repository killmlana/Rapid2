FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY vila/requirements.txt /app/vila-requirements.txt
RUN pip install --no-cache-dir -r /app/vila-requirements.txt

COPY vila/examples/end2end-sci-pdf-parsing/requirements.txt /app/service-requirements.txt
RUN pip install --no-cache-dir -r /app/service-requirements.txt

COPY vila/ /app/vila/
RUN pip install --no-cache-dir -e /app/vila/

COPY vila/examples/end2end-sci-pdf-parsing/ /app/service/

RUN python -c "from transformers import AutoTokenizer, AutoModelForTokenClassification; \
    AutoTokenizer.from_pretrained('allenai/ivila-row-layoutlm-finetuned-s2vl-v2'); \
    AutoModelForTokenClassification.from_pretrained('allenai/ivila-row-layoutlm-finetuned-s2vl-v2')"

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

CMD ["uvicorn", "service.vila_pdf_parsing_service:app", "--host", "0.0.0.0", "--port", "8080"]
