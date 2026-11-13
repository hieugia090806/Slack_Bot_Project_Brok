# SUMMARY: Layer 2 Chunking & Embedding generation pipeline.
"""Dependency-light chunking and embeddings for local and hosted execution."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re

logger = logging.getLogger(__name__)
VECTOR_DIMENSIONS = 384
EMBEDDING_MODEL = "text-embedding-3-small"


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 200) -> list[str]:
    """Split normalized text into overlapping character windows."""
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap smaller than chunk_size")
    normalized_text = " ".join((text or "").split())
    if not normalized_text:
        return []
    step = chunk_size - overlap
    return [normalized_text[start : start + chunk_size] for start in range(0, len(normalized_text), step)]


def _local_embedding(text: str) -> list[float]:
    """Create a deterministic normalized feature-hash embedding without a service."""
    vector = [0.0] * VECTOR_DIMENSIONS
    terms = re.findall(r"[\w'-]+", text.lower())
    features = terms + [f"{left}_{right}" for left, right in zip(terms, terms[1:])]
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % VECTOR_DIMENSIONS
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def generate_embeddings(chunks: list[str]) -> list[list[float]]:
    """Return OpenAI embeddings when configured, otherwise local feature hashes.

    Missing SDKs, absent credentials, and API errors all fall back locally so
    indexing and queries remain usable without external services.
    """
    if not chunks:
        return []
    if os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI

            response = OpenAI().embeddings.create(
                model=EMBEDDING_MODEL,
                input=chunks,
                dimensions=VECTOR_DIMENSIONS,
            )
            return [list(item.embedding) for item in sorted(response.data, key=lambda item: item.index)]
        except Exception:
            logger.warning("Remote embeddings unavailable; using local embeddings", exc_info=True)
    return [_local_embedding(chunk) for chunk in chunks]
