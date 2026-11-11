# SUMMARY: Slack Delivery Zone Block Kit formatter for rich cards and citations.
"""Build Slack Block Kit messages with readable answers and source citations."""

from __future__ import annotations

import re

_MAX_SECTION_CHARS = 3000


def _source_badge(source: str) -> str:
    """Render a clickable Slack link when a source has an absolute web URL."""
    value = source.strip()
    slack_link = re.fullmatch(r"<([^>|]+)\|([^>]+)>", value)
    if slack_link:
        url, label = slack_link.groups()
    else:
        match = re.fullmatch(r"(.+?)\s*\((https?://[^)]+)\)", value)
        if match:
            label, url = match.groups()
        elif value.startswith(("https://", "http://")):
            url, label = value, value
        else:
            return f"📄 {value}"
    if url.startswith(("https://", "http://")):
        return f"<{url}|📄 {label}>"
    return f"📄 {label}"


def build_slack_blocks(answer: str, sources: list[str]) -> list[dict]:
    """Create a compact Block Kit card with an answer and citation badges."""
    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": (answer or "I could not generate an answer.")[:_MAX_SECTION_CHARS]}}
    ]
    badges = [_source_badge(source) for source in sources if source.strip()]
    for start in range(0, len(badges), 10):
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": badge[:2000]} for badge in badges[start : start + 10]
        ]})
    return blocks[:50]
