import hashlib
import re
from pathlib import Path
from typing import Any

from src.vector_store import SQLiteVectorStore, get_vector_store

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

MOCK_DOCS_DIR = Path(__file__).resolve().parents[1] / "mock_docs"


def load_local_mock_docs() -> list[dict[str, Any]]:
    pages = []
    for path in sorted(MOCK_DOCS_DIR.glob("*.md")):
        source = path.relative_to(MOCK_DOCS_DIR.parent).as_posix()
        pages.append(
            {
                "text": path.read_text(encoding="utf-8-sig"),
                "metadata": {
                    "page_id": source,
                    "title": path.stem.replace("_", " ").replace("-", " ").title(),
                    "url": source,
                    "source": source,
                },
            }
        )
    return pages


def _fallback_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    words = re.findall(r"\S+", text)
    if not words:
        return []
    step = max(1, chunk_size - chunk_overlap)
    return [" ".join(words[start : start + chunk_size]) for start in range(0, len(words), step)]


def chunk_documents(
    pages: list[dict[str, Any]], chunk_size: int = 512, chunk_overlap: int = 200
) -> list[dict[str, Any]]:
    try:
        from llama_index.core.node_parser import SentenceSplitter

        splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        split_text = splitter.split_text
    except ImportError:
        split_text = lambda text: _fallback_split(text, chunk_size, chunk_overlap)

    chunks = []
    for page in pages:
        metadata = page["metadata"]
        for index, content in enumerate(split_text(page["text"])):
            if not content.strip():
                continue
            chunk_metadata = {**metadata, "chunk_index": index}
            chunk_id = hashlib.sha256(
                f"{metadata['page_id']}:{index}".encode("utf-8")
            ).hexdigest()
            chunks.append(
                {"id": chunk_id, "content": content, "metadata": chunk_metadata}
            )
    return chunks


def ingest_local_docs(store: SQLiteVectorStore | None = None) -> int:
    chunks = chunk_documents(load_local_mock_docs())
    return (store or get_vector_store()).upsert(chunks)


if __name__ == "__main__":
    count = ingest_local_docs()
    print(f"Indexed {count} chunks from {MOCK_DOCS_DIR}")