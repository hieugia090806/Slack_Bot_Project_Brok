"""MemTrust Layer 1 extraction and Layer 2 handoff.

Fetches approved Confluence spaces over REST v2, sanitizes and masks their
storage bodies, preserves page provenance, and submits non-empty sentence
chunks to the vector store. No RA-TLS transport stub is implemented here.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from src.vector_store import InMemoryVectorStore, PostgresVectorStore, get_vector_store
    from src.embedding import chunk_text
    from src.sanitization import sanitize_and_mask
    from src.space_config import get_target_spaces
except ModuleNotFoundError:
    from vector_store import InMemoryVectorStore, PostgresVectorStore, get_vector_store
    from embedding import chunk_text
    from sanitization import sanitize_and_mask
    from space_config import get_target_spaces

TIMEOUT_SECONDS = 20
_HISTORICAL_MARKER = re.compile(r"\b(?:archived|superseded|legacy)\b", re.IGNORECASE)


def _is_historical_page(title: str, body: str) -> bool:
    """Identify archived, superseded, or explicitly legacy page content."""
    return bool(_HISTORICAL_MARKER.search(f"{title}\n{body}"))


def _credentials() -> tuple[str, str, str] | None:
    """Read only explicitly configured Confluence credentials; never invent defaults."""
    url = os.getenv("CONFLUENCE_URL", "").strip().rstrip("/")
    username = os.getenv("CONFLUENCE_USERNAME", "").strip()
    token = os.getenv("CONFLUENCE_API_TOKEN", "").strip()
    missing = [
        name for name, value in (
            ("CONFLUENCE_URL", url),
            ("CONFLUENCE_USERNAME", username),
            ("CONFLUENCE_API_TOKEN", token),
        ) if not value
    ]
    if missing:
        print(f"WARNING: Missing Confluence configuration: {', '.join(missing)}.")
        return None
    return url, username, token


def _get_space_id(
    session: requests.Session, base_url: str, auth: HTTPBasicAuth, space_key: str
) -> tuple[str | None, int]:
    response = session.get(
        f"{base_url}/api/v2/spaces", params={"keys": space_key, "limit": 1},
        auth=auth, headers={"Accept": "application/json"}, timeout=TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        if response.status_code in (401, 403):
            print(
                f"WARNING: Confluence space lookup denied for {space_key}: "
                f"HTTP {response.status_code}; check credentials and space permissions."
            )
        else:
            print(f"Confluence space lookup failed: HTTP {response.status_code} - {response.text}")
        return None, response.status_code
    spaces = response.json().get("results", [])
    return (str(spaces[0]["id"]) if spaces and spaces[0].get("id") else None), response.status_code


def _fetch_pages(
    session: requests.Session, base_url: str, auth: HTTPBasicAuth, space_key: str
) -> tuple[list[dict[str, Any]], int | None, int]:
    space_id, space_status = _get_space_id(session, base_url, auth, space_key)
    if not space_id:
        if space_status == 200:
            print(f"WARNING: Confluence space {space_key} was not found or is not visible to this account.")
            # Treat a missing configured space as incomplete; never prune its snapshot.
            return [], None, 0
        return [], space_status, 0

    url = f"{base_url}/api/v2/pages"
    params: dict[str, Any] | None = {"space-id": space_id, "body-format": "storage", "limit": 100}
    pages: list[dict[str, Any]] = []
    status_code: int | None = None
    filtered_count = 0
    while url:
        response = session.get(
            url, params=params, auth=auth, headers={"Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
        )
        status_code = response.status_code
        if status_code != 200:
            if status_code in (401, 403):
                print(
                    f"WARNING: Confluence page fetch denied for space {space_key}: "
                    f"HTTP {status_code}; check credentials and space permissions."
                )
            else:
                print(f"Confluence page fetch failed: HTTP {status_code} - {response.text}")
            return pages, status_code, filtered_count

        data = response.json()
        for item in data.get("results", []):
            page_id = item.get("id")
            if not page_id:
                continue
            body = item.get("body", {}).get("storage", {}).get("value", "")
            title = item.get("title") or "Untitled"
            if _is_historical_page(title, body):
                filtered_count += 1
                continue
            text = sanitize_and_mask(body)
            pages.append({
                "text": text,
                "metadata": {
                    "page_id": str(page_id),
                    "title": title,
                    "url": f"{base_url}/spaces/{space_key}/pages/{page_id}",
                    "source_url": f"{base_url}/spaces/{space_key}/pages/{page_id}",
                    "source": "confluence",
                    "space_key": space_key,
                    "security_level": "internal",
                },
            })
        next_url = data.get("_links", {}).get("next")
        if not next_url:
            links = response.links
            next_url = links.get("next", {}).get("url")
        url = urljoin(base_url + "/", next_url) if next_url else ""
        params = None  # Cursor is encoded in the next URL.
    return pages, status_code, filtered_count


def fetch_confluence_pages() -> list[dict[str, Any]]:
    """Fetch active pages from every configured Confluence space."""
    credentials = _credentials()
    if not credentials:
        return []
    base_url, username, token = credentials
    target_spaces = get_target_spaces()
    try:
        session = requests.Session()
        pages: list[dict[str, Any]] = []
        filtered_count = 0
        for space_key in target_spaces:
            space_pages, status, filtered = _fetch_pages(
                session, base_url, HTTPBasicAuth(username, token), space_key
            )
            if status != 200:
                raise RuntimeError(f"Confluence fetch failed for space {space_key}: HTTP {status}")
            pages.extend(space_pages)
            filtered_count += filtered
        sanitized_count = sum(bool(page.get("text", "").strip()) for page in pages)
        print(f"Confluence {target_spaces}: fetched {len(pages)} active pages; filtered archived/superseded pages: {filtered_count}; sanitized non-empty pages: {sanitized_count}.")
        return pages
    except (requests.RequestException, ValueError, KeyError, RuntimeError) as exc:
        print(f"Error connecting to Confluence API: {exc}")
        return []


def _fetch_confluence_snapshot() -> tuple[dict[str, list[dict[str, Any]]], dict[str, bool], dict[str, int]]:
    """Fetch a complete active snapshot for each configured space independently."""
    credentials = _credentials()
    target_spaces = get_target_spaces()
    if not credentials:
        return {}, {space: False for space in target_spaces}, {space: 0 for space in target_spaces}
    base_url, username, token = credentials
    session = requests.Session()
    pages_by_space: dict[str, list[dict[str, Any]]] = {}
    complete_by_space: dict[str, bool] = {}
    filtered_by_space: dict[str, int] = {}
    try:
        auth = HTTPBasicAuth(username, token)
        for space_key in target_spaces:
            pages, status_code, filtered_count = _fetch_pages(session, base_url, auth, space_key)
            pages_by_space[space_key] = pages
            complete_by_space[space_key] = status_code == 200
            filtered_by_space[space_key] = filtered_count
        return pages_by_space, complete_by_space, filtered_by_space
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"Error connecting to Confluence API: {exc}")
        return pages_by_space, {space: False for space in target_spaces}, filtered_by_space


def test_confluence_connection() -> dict[str, Any]:
    """Print a diagnostic status and page count for the configured live space."""
    credentials = _credentials()
    if not credentials:
        print("Confluence diagnostic: credentials missing; cannot connect.")
        return {"status_code": None, "page_count": 0, "ok": False}
    base_url, username, token = credentials
    target_spaces = get_target_spaces()
    try:
        session = requests.Session()
        pages: list[dict[str, Any]] = []
        filtered_count = 0
        statuses: dict[str, int | None] = {}
        for space_key in target_spaces:
            space_pages, status_code, filtered = _fetch_pages(
                session, base_url, HTTPBasicAuth(username, token), space_key
            )
            statuses[space_key] = status_code
            pages.extend(space_pages)
            filtered_count += filtered
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"Confluence diagnostic connection error: {exc}")
        return {"status_code": None, "page_count": 0, "ok": False}
    print(f"Confluence space statuses: {statuses}")
    print(f"Active pages in {target_spaces}: {len(pages)}; archived/superseded filtered: {filtered_count}")
    for space_key, status_code in statuses.items():
        if status_code in (401, 403):
            print(f"WARNING: HTTP {status_code} Unauthorized/Forbidden for {space_key}; check credentials and access.")
    ok = all(status == 200 for status in statuses.values()) and len(statuses) == len(target_spaces)
    return {"status_code": statuses, "page_count": len(pages), "ok": ok}


def split_text(text: str, chunk_size: int = 512, chunk_overlap: int = 64) -> list[str]:
    return chunk_text(text, chunk_size=chunk_size, overlap=chunk_overlap)


def chunk_documents(
    pages: list[dict[str, Any]], chunk_size: int = 512, chunk_overlap: int = 64
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for page in pages:
        metadata = dict(page.get("metadata", {}))
        if _is_historical_page(str(metadata.get("title", "")), str(page.get("text", ""))):
            continue
        page_id = str(metadata.get("page_id") or "document")
        for index, content in enumerate(split_text(page.get("text", ""), chunk_size, chunk_overlap)):
            space_key = str(metadata.get("space_key") or "")
            chunk_id = hashlib.sha256(f"{space_key}:{page_id}:{index}".encode("utf-8")).hexdigest()
            chunks.append({"id": chunk_id, "content": content, "metadata": {**metadata, "chunk_index": index}})
    return chunks


def ingest_local_docs(
    store: PostgresVectorStore | InMemoryVectorStore | None = None,
    trigger: str = "manual",
) -> int:
    """Fetch and replace complete snapshots for all configured spaces."""
    started_at = time.time()
    synced_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    target_spaces = get_target_spaces()
    print(f"🔄 [Sync] Started at {synced_at} | Trigger: {trigger} | Effective spaces: {target_spaces}", flush=True)
    try:
        pages_by_space, complete_by_space, filtered_by_space = _fetch_confluence_snapshot()
        vector_store = store or get_vector_store()
        indexed_count = 0
        failed_spaces = []
        active_pages = 0
        filtered_count = 0
        for space_key in target_spaces:
            if not complete_by_space.get(space_key, False):
                failed_spaces.append(space_key)
                continue
            pages = pages_by_space.get(space_key, [])
            active_pages += len(pages)
            filtered_count += filtered_by_space.get(space_key, 0)
            indexed_count += vector_store.sync_space_documents(chunk_documents(pages), space_key)
        if failed_spaces:
            raise RuntimeError(f"Confluence sync incomplete for spaces: {', '.join(failed_spaces)}")
        duration = time.time() - started_at
        print(
            f"✅ [Sync] Status: Success | Freshness: {synced_at} | "
            f"Trigger: {trigger} | "
            f"Spaces: {target_spaces} | Active pages: {active_pages} | Active chunks indexed: {indexed_count} | "
            f"Archived/superseded pages filtered: {filtered_count} | "
            f"Stale page/chunk pruning: completed | Duration: {duration:.2f}s",
            flush=True,
        )
        return indexed_count
    except Exception as exc:
        duration = time.time() - started_at
        print(
            f"❌ [Sync] Status: Failed | Freshness: {synced_at} | "
            f"Trigger: {trigger} | "
            f"Stale snapshot preserved: yes | Duration: {duration:.2f}s | Error: {exc}",
            flush=True,
        )
        raise


if __name__ == "__main__":
    import sys

    if "--check" in sys.argv:
        test_confluence_connection()
    else:
        print(f"Loading documents from configured Confluence spaces {get_target_spaces()}...")
        print(f"Successfully added {ingest_local_docs()} chunks to the vector store.")
