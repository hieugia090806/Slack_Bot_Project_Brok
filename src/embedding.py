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
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_BATCH_SIZE = 50


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 200) -> list[str]:
    """Split on sentence boundaries with approximate token windows and overlap."""
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap smaller than chunk_size")
    sentences = re.split(r"(?<=[.!?])\s+", " ".join((text or "").split()))
    sentences = [sentence for sentence in sentences if sentence]
    if not sentences:
        return []
    chunks: list[str] = []
    current: list[str] = []
    count = 0
    for sentence in sentences:
        sentence_tokens = len(re.findall(r"\w+|[^\w\s]", sentence))
        if current and count + sentence_tokens > chunk_size:
            chunks.append(" ".join(current))
            tail: list[str] = []
            tail_count = 0
            for previous in reversed(current):
                previous_count = len(re.findall(r"\w+|[^\w\s]", previous))
                if tail_count + previous_count > overlap:
                    break
                tail.insert(0, previous)
                tail_count += previous_count
            current, count = tail, tail_count
        current.append(sentence)
        count += sentence_tokens
    if current:
        chunks.append(" ".join(current))
    return chunks


def generate_sparse_embeddings(texts: list[str]) -> list[dict[str, float]]:
    """Return normalized term-frequency vectors for sparse retrieval."""
    sparse = []
    for text in texts:
        counts: dict[str, float] = {}
        for term in re.findall(r"[\w'-]+", text.lower()):
            counts[term] = counts.get(term, 0.0) + 1.0
        norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
        sparse.append({term: value / norm for term, value in counts.items()})
    return sparse


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
    """Return Gemini dense embeddings or deterministic local feature hashes.

    Missing SDKs, absent credentials, and API errors all fall back locally so
    indexing and queries remain usable without external services.
    """
    if not chunks:
        return []
    api_key = os.getenv("SLACK_API_KEY")
    if api_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=15_000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            vectors = []
            for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
                batch_texts = chunks[start : start + EMBEDDING_BATCH_SIZE]
                result = client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=batch_texts,
                    config=types.EmbedContentConfig(output_dimensionality=VECTOR_DIMENSIONS),
                )
                if not result.embeddings or len(result.embeddings) != len(batch_texts):
                    raise ValueError("Gemini returned an incomplete embedding batch")
                vectors.extend(list(item.values) for item in result.embeddings)
            logger.info("Gemini embeddings active with model %s", EMBEDDING_MODEL)
            return vectors
        except Exception:
            logger.warning("Gemini embeddings failed; using local embeddings", exc_info=True)
    else:
        logger.info("SLACK_API_KEY missing; Gemini embeddings disabled, using local embeddings")
    return [_local_embedding(chunk) for chunk in chunks]
