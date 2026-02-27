"""
Retriever with optional Maximal Marginal Relevance (MMR) re-ranking.

MMR balances relevance to the query with diversity among returned chunks,
reducing redundant retrieval from repeated passages in source documents.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass

from tdrcreator.ingest.chunker import Chunk
from tdrcreator.retrieval.embedder import embed_query
from tdrcreator.retrieval.index import ChunkIndex
from tdrcreator.security.logger import get_logger

_log = get_logger("retrieval.retriever")


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float          # relevance score (cosine similarity, 0–1)
    mmr_score: float      # final MMR score (if MMR applied, else == score)


def retrieve(
    query: str,
    index: ChunkIndex,
    model_name: str,
    top_k: int = 8,
    mmr: bool = True,
    mmr_lambda: float = 0.6,
    fetch_k: int | None = None,
) -> list[RetrievedChunk]:
    """
    Retrieve top_k chunks for `query` from `index`.

    Args:
        query:       Natural-language query string.
        index:       Loaded ChunkIndex.
        model_name:  Embedding model to encode the query.
        top_k:       Number of chunks to return.
        mmr:         Use Maximal Marginal Relevance re-ranking.
        mmr_lambda:  MMR tradeoff: 1.0 = pure relevance, 0.0 = pure diversity.
        fetch_k:     Candidates fetched before MMR (default: 4 * top_k).
    """
    q_emb = embed_query(query, model_name)  # shape (1, D)

    if fetch_k is None:
        fetch_k = max(top_k * 4, 20)

    candidates = index.search(q_emb, top_k=fetch_k)

    if not candidates:
        return []

    if not mmr or len(candidates) <= top_k:
        results = candidates[:top_k]
        return [RetrievedChunk(c, s, s) for c, s in results]

    # ----- MMR -----
    candidate_embeddings = _get_embeddings_for(
        [c for c, _ in candidates], model_name
    )
    q_vec = q_emb[0]

    selected_indices: list[int] = []
    remaining = list(range(len(candidates)))

    for _ in range(top_k):
        if not remaining:
            break
        if not selected_indices:
            # First: pick most relevant
            best = max(remaining, key=lambda i: candidates[i][1])
        else:
            selected_embs = candidate_embeddings[selected_indices]

            def mmr_score(i: int) -> float:
                rel = float(candidates[i][1])
                sim_to_selected = float(
                    np.max(candidate_embeddings[i] @ selected_embs.T)
                )
                return mmr_lambda * rel - (1 - mmr_lambda) * sim_to_selected

            best = max(remaining, key=mmr_score)

        selected_indices.append(best)
        remaining.remove(best)

    results = []
    for idx in selected_indices:
        chunk, score = candidates[idx]
        results.append(RetrievedChunk(chunk=chunk, score=score, mmr_score=score))

    _log.metric("retrieve", query_hash=hash(query) & 0xFFFF, returned=len(results))
    return results


def _get_embeddings_for(chunks: list[Chunk], model_name: str) -> np.ndarray:
    from tdrcreator.retrieval.embedder import embed_texts
    texts = [c.text for c in chunks]
    return embed_texts(texts, model_name)
