# SUMMARY: Layer 3 Governance & Access Policy Engine stub for Katalon.
"""Prototype document authorization seam, ready for a future OPA adapter."""

from __future__ import annotations

from typing import Any


def check_access(user_email: str, document_metadata: dict[str, Any]) -> bool:
    """Allow access by default for the prototype.

    Keep user and document context in the function contract so an OPA or
    organization-specific policy decision can replace this permissive default.
    """
    del user_email, document_metadata
    return True
