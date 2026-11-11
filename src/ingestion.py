# SUMMARY: Scans mock_docs/ for markdown files, parses them into searchable chunks, and populates the vector store.
"""Load local markdown knowledge files and add their chunks to the vector store.

Run from the repository root with ``python src/ingestion.py``. If
``DATABASE_URL`` is configured, the store writes to PostgreSQL/pgvector; without
it, chunks are loaded into an in-memory store for local execution.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from src.vector_store import InMemoryVectorStore, PostgresVectorStore, get_vector_store
    from src.embedding import chunk_text
    from src.sanitization import sanitize_and_mask
except ModuleNotFoundError:  # Supports the documented ``python src/ingestion.py`` command.
    from vector_store import InMemoryVectorStore, PostgresVectorStore, get_vector_store
    from embedding import chunk_text
    from sanitization import sanitize_and_mask

MOCK_DOCS_DIR = Path(__file__).resolve().parents[1] / "mock_docs"


def load_markdown_documents(directory: Path = MOCK_DOCS_DIR) -> list[dict[str, Any]]:
    """Read all markdown files recursively, preserving useful source metadata."""
    pages: list[dict[str, Any]] = []
    if not directory.exists():
        return pages
    for path in sorted(directory.rglob("*.md")):
        relative_path = path.relative_to(directory).as_posix()
        source = f"mock_docs/{relative_path}"
        pages.append(
            {
                "text": sanitize_and_mask(path.read_text(encoding="utf-8-sig")),
                "metadata": {
                    "page_id": source,
                    "title": path.stem.replace("_", " ").replace("-", " ").title(),
                    "url": source,
                    "source": source,
                },
            }
        )
    return pages


def split_text(text: str, chunk_size: int = 512, chunk_overlap: int = 64) -> list[str]:
    """Compatibility wrapper around the shared Layer 2 chunking pipeline."""
    return chunk_text(text, chunk_size=chunk_size, overlap=chunk_overlap)


def chunk_documents(
    pages: list[dict[str, Any]], chunk_size: int = 512, chunk_overlap: int = 64
) -> list[dict[str, Any]]:
    """Convert pages into stable, uniquely identified chunk records."""
    chunks: list[dict[str, Any]] = []
    for page in pages:
        metadata = dict(page.get("metadata", {}))
        page_id = str(metadata.get("page_id") or metadata.get("source") or "document")
        for index, content in enumerate(split_text(page.get("text", ""), chunk_size, chunk_overlap)):
            chunk_id = hashlib.sha256(f"{page_id}:{index}".encode("utf-8")).hexdigest()
            chunks.append(
                {"id": chunk_id, "content": content, "metadata": {**metadata, "chunk_index": index}}
            )
    return chunks


def ingest_local_docs(
    store: PostgresVectorStore | InMemoryVectorStore | None = None,
    directory: Path = MOCK_DOCS_DIR,
) -> int:
    """Read, chunk, and add all local markdown documents; return chunks added."""
    chunks = chunk_documents(load_markdown_documents(directory))
    if not chunks:
        return 0
    return (store or get_vector_store()).add_documents(chunks)


if __name__ == "__main__":
    print(f"Loading markdown documents from {MOCK_DOCS_DIR}...")
    added = ingest_local_docs()
    print(f"Successfully added {added} chunks to the vector store.")
