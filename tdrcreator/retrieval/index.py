"""
FAISS-based local vector index.

The index stores:
  - A FAISS flat L2 index (cosine via normalised vectors)
  - A parallel list of Chunk metadata (pickled)
  - A mapping from chunk_id → index position (for deduplication)

Everything stays on disk in `index_dir`; no cloud storage involved.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import numpy as np

from tdrcreator.ingest.chunker import Chunk
from tdrcreator.retrieval.embedder import embed_texts
from tdrcreator.security.logger import get_logger

_log = get_logger("retrieval.index")

_INDEX_FILE = "faiss.index"
_CHUNKS_FILE = "chunks.pkl"
_META_FILE = "index_meta.json"


class ChunkIndex:
    """
    Wrapper around a FAISS index with chunk metadata lookup.
    """

    def __init__(self) -> None:
        self._index = None          # faiss.Index
        self._chunks: list[Chunk] = []
        self._id_to_pos: dict[str, int] = {}  # chunk_id → list position

    # ------------------------------------------------------------------
    # Building / updating
    # ------------------------------------------------------------------

    def add(self, chunks: list[Chunk], embeddings: np.ndarray) -> int:
        """
        Add chunks + embeddings to the index.  Deduplicates by chunk_id.
        Returns number of newly added chunks.
        """
        try:
            import faiss
        except ImportError as e:
            raise RuntimeError(
                "faiss-cpu not installed – run: pip install faiss-cpu"
            ) from e

        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have same length"
            )

        new_chunks: list[Chunk] = []
        new_embeddings: list[np.ndarray] = []

        for chunk, emb in zip(chunks, embeddings):
            if chunk.chunk_id not in self._id_to_pos:
                self._id_to_pos[chunk.chunk_id] = len(self._chunks) + len(new_chunks)
                new_chunks.append(chunk)
                new_embeddings.append(emb)

        if not new_chunks:
            _log.info("No new chunks to add (all duplicates)")
            return 0

        dim = embeddings.shape[1]
        if self._index is None:
            self._index = faiss.IndexFlatIP(dim)  # inner product = cosine (normalised)

        matrix = np.stack(new_embeddings).astype(np.float32)
        self._index.add(matrix)  # type: ignore[union-attr]
        self._chunks.extend(new_chunks)

        _log.metric("index.add", new=len(new_chunks), total=len(self._chunks))
        return len(new_chunks)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def search(self, query_embedding: np.ndarray, top_k: int) -> list[tuple[Chunk, float]]:
        """
        Return the top_k nearest chunks with their similarity scores.
        query_embedding: shape (1, D) or (D,)
        """
        if self._index is None or len(self._chunks) == 0:
            return []

        qe = query_embedding.reshape(1, -1).astype(np.float32)
        k = min(top_k, len(self._chunks))
        scores, indices = self._index.search(qe, k)  # type: ignore[union-attr]

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            results.append((self._chunks[idx], float(score)))
        return results

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, index_dir: Path) -> None:
        try:
            import faiss
        except ImportError as e:
            raise RuntimeError("faiss-cpu not installed") from e

        index_dir.mkdir(parents=True, exist_ok=True)
        if self._index is not None:
            faiss.write_index(self._index, str(index_dir / _INDEX_FILE))

        with open(index_dir / _CHUNKS_FILE, "wb") as fh:
            pickle.dump(self._chunks, fh)

        meta = {
            "num_chunks": len(self._chunks),
            "dim": self._index.d if self._index else 0,
        }
        (index_dir / _META_FILE).write_text(json.dumps(meta, indent=2))
        _log.metric("index.save", chunks=len(self._chunks), dir=str(index_dir))

    @classmethod
    def load(cls, index_dir: Path) -> "ChunkIndex":
        try:
            import faiss
        except ImportError as e:
            raise RuntimeError("faiss-cpu not installed") from e

        obj = cls()
        idx_file = index_dir / _INDEX_FILE
        chunks_file = index_dir / _CHUNKS_FILE

        if not idx_file.exists() or not chunks_file.exists():
            raise FileNotFoundError(
                f"Index not found at {index_dir}. Run `tdrcreator ingest` first."
            )

        obj._index = faiss.read_index(str(idx_file))
        with open(chunks_file, "rb") as fh:
            obj._chunks = pickle.load(fh)
        obj._id_to_pos = {c.chunk_id: i for i, c in enumerate(obj._chunks)}
        _log.metric("index.load", chunks=len(obj._chunks))
        return obj

    @staticmethod
    def exists(index_dir: Path) -> bool:
        return (index_dir / _INDEX_FILE).exists()

    def chunk_count(self) -> int:
        return len(self._chunks)

    def all_chunks(self) -> list[Chunk]:
        return list(self._chunks)


# ---------------------------------------------------------------------------
# Convenience builder
# ---------------------------------------------------------------------------

def build_index(
    chunks: list[Chunk],
    model_name: str,
    index_dir: Path,
    batch_size: int = 64,
) -> ChunkIndex:
    """Embed all chunks, build FAISS index, save to disk."""
    texts = [c.text for c in chunks]
    _log.info(f"Embedding {len(texts)} chunk(s) …")
    embeddings = embed_texts(texts, model_name, batch_size=batch_size)

    idx = ChunkIndex()
    # Load existing index if present (incremental update)
    if ChunkIndex.exists(index_dir):
        idx = ChunkIndex.load(index_dir)

    added = idx.add(chunks, embeddings)
    idx.save(index_dir)
    _log.metric("build_index", added=added, total=idx.chunk_count())
    return idx
