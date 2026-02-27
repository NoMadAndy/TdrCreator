"""
Local embedding model via sentence-transformers.

All embedding is performed locally – the model weights are downloaded from
HuggingFace Hub once and cached; after that no network access is needed.
Embedding calls NEVER send document text to any external service.
"""

from __future__ import annotations

import numpy as np
from typing import TYPE_CHECKING

from tdrcreator.security.logger import get_logger

if TYPE_CHECKING:
    from numpy.typing import NDArray

_log = get_logger("retrieval.embedder")

# Singleton model cache per process
_model_cache: dict[str, object] = {}


def load_model(model_name: str):
    """Load (and cache) a SentenceTransformer model."""
    if model_name not in _model_cache:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "sentence-transformers not installed – run: pip install sentence-transformers"
            ) from e
        _log.info(f"Loading embedding model: {model_name}")
        _model_cache[model_name] = SentenceTransformer(model_name)
        _log.info(f"Embedding model loaded: {model_name}")
    return _model_cache[model_name]


def embed_texts(texts: list[str], model_name: str, batch_size: int = 64) -> "NDArray":
    """
    Embed a list of text strings and return an (N, D) float32 numpy array.

    Args:
        texts:      List of strings to embed.
        model_name: SentenceTransformer model identifier.
        batch_size: Batch size for GPU/CPU efficiency.

    Returns:
        numpy array of shape (len(texts), embedding_dim).
    """
    if not texts:
        return np.empty((0, 384), dtype=np.float32)

    model = load_model(model_name)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,  # cosine similarity = dot product
    )
    _log.metric("embed_texts", n=len(texts), dim=embeddings.shape[1])
    return embeddings.astype(np.float32)


def embed_query(query: str, model_name: str) -> "NDArray":
    """Embed a single query string; returns shape (1, D)."""
    return embed_texts([query], model_name)
