# SUMMARY: Layer 3 Governance & Access Policy Engine for document retrieval authorization.
"""Document authorization policy engine supporting student role-based access control (RBAC).

Maps user emails (such as team @swin.edu addresses) to access levels and compares
them against document metadata security classifications.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Security level hierarchy (higher index = higher clearance level required)
SECURITY_LEVELS = {
    "public": 1,
    "internal": 2,
    "confidential": 3,
    "restricted": 4,
}

# Role clearance levels
ROLE_CLEARANCE = {
    "admin": 4,
    "developer": 3,
    "employee": 2,
    "student": 1,
    "guest": 1,
}

# Mock user mapping for development and team testing
# Replace or extend these email addresses with your team members' actual emails
MOCK_USER_ROLES: dict[str, str] = {
    "hoang@swin.edu": "admin",
    "hieu@swin.edu": "developer",
    "ny@swin.edu": "developer",
    "khai@swin.edu": "employee",
    "minhhoang@swin.edu": "employee",
    "nhat@swin.edu": "student",
}


def get_user_role(user_email: str) -> str:
    """Resolve a user email to their role, defaulting to 'student' for unknown emails."""
    normalized_email = user_email.strip().lower()
    return MOCK_USER_ROLES.get(normalized_email, "student")


def check_access(user_email: str, document_metadata: dict[str, Any]) -> bool:
    """Evaluate whether a user email has authorization to view a document chunk.

    Compares user clearance level against document security classification.
    Defaults to 'public' clearance check if metadata does not specify security_level.
    """
    if not user_email:
        logger.warning("Empty user email provided for policy check. Access denied.")
        return False

    # Get document classification (default to 'public' if not specified)
    doc_level = str(document_metadata.get("security_level", "public")).lower()
    required_clearance = SECURITY_LEVELS.get(doc_level, 1)

    # Determine user role and clearance
    role = get_user_role(user_email)
    user_clearance = ROLE_CLEARANCE.get(role, 1)

    # Allow access if user clearance is equal to or higher than document requirements
    is_allowed = user_clearance >= required_clearance

    logger.debug(
        "Policy check for user=%s (role=%s, clearance=%d) vs doc_level=%s (req=%d) -> %s",
        user_email,
        role,
        user_clearance,
        doc_level,
        required_clearance,
        "ALLOWED" if is_allowed else "DENIED",
    )

    return is_allowed