#!/bin/bash
set -e

DATA_DIR="${TDR_DATA_DIR:-/data}"

echo "=== TdrCreator Web ==="
echo "Data dir: $DATA_DIR"

# Ensure data directories exist
mkdir -p "$DATA_DIR/docs" "$DATA_DIR/out"

# Pre-download the embedding model if not cached
CACHE_DIR="${HF_HOME:-/root/.cache/huggingface}"
MODEL_NAME="${EMBEDDING_MODEL:-sentence-transformers/all-MiniLM-L6-v2}"

if [ ! -d "$CACHE_DIR/hub" ]; then
  echo "Pre-downloading embedding model: $MODEL_NAME"
  python -c "
from sentence_transformers import SentenceTransformer
import os
model_name = os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
try:
    SentenceTransformer(model_name)
    print(f'Model {model_name} ready.')
except Exception as e:
    print(f'Warning: Could not pre-download model: {e}')
" || true
fi

echo "Starting TdrCreator Web on 0.0.0.0:${TDR_PORT:-8000}..."
exec uvicorn tdrcreator.webapp.api:app \
  --host "${TDR_HOST:-0.0.0.0}" \
  --port "${TDR_PORT:-8000}" \
  --workers 1 \
  --log-level info
