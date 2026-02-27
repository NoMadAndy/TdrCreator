# ─────────────────────────────────────────────────────────────────────────────
# TdrCreator – Docker Image
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# System dependencies for pypdf, lxml, python-docx
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e ".[webapp]"

# Copy application source
COPY tdrcreator/ tdrcreator/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Data volume (docs, index, output, config)
VOLUME ["/data"]

# HuggingFace model cache
VOLUME ["/root/.cache/huggingface"]

EXPOSE 8000

ENV TDR_DATA_DIR=/data \
    TDR_HOST=0.0.0.0 \
    TDR_PORT=8000 \
    HF_HOME=/root/.cache/huggingface \
    TOKENIZERS_PARALLELISM=false \
    # Prevents sentence-transformers from trying to update online
    TRANSFORMERS_OFFLINE=0

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${TDR_PORT:-8000}/api/health || exit 1

ENTRYPOINT ["./entrypoint.sh"]
