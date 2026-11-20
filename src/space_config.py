"""Shared configuration for the Confluence spaces used by ingestion and search."""

from __future__ import annotations

import os

DEFAULT_SPACE_KEYS = ("COS40005",)


def get_target_spaces() -> list[str]:
    """Parse supported Confluence space settings in precedence order.

    Both singular and plural environment variable names are used by existing
    deployments. When both are set, combine them while preserving their order.
    """
    spaces: list[str] = []
    for name in ("CONFLUENCE_SPACE_KEYS", "CONFLUENCE_SPACE_KEY"):
        raw_keys = os.getenv(name, "")
        for value in raw_keys.split(","):
            key = value.strip().upper()
            if key and key not in spaces:
                spaces.append(key)
    return spaces or list(DEFAULT_SPACE_KEYS)
