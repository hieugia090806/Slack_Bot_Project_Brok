"""Shared configuration for the Confluence spaces used by ingestion and search."""

from __future__ import annotations

import os

DEFAULT_SPACE_KEYS = ("COS40005",)


def get_target_spaces() -> list[str]:
    """Parse configured Confluence keys, preserving order and removing duplicates."""
    raw_keys = os.getenv("CONFLUENCE_SPACE_KEYS")
    if raw_keys is None or not raw_keys.strip():
        return list(DEFAULT_SPACE_KEYS)
    spaces = list(dict.fromkeys(key.strip() for key in raw_keys.split(",") if key.strip()))
    return spaces or list(DEFAULT_SPACE_KEYS)
