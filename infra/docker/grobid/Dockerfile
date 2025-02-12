FROM grobid/grobid:0.8.1

EXPOSE 8070

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8070/api/isalive || exit 1
