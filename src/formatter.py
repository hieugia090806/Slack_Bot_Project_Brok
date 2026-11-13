# SUMMARY: Slack Delivery Zone Block Kit formatter for rich cards and citations.
"""AIRA Layer 4 presentation: render generated answers and source metadata in Block Kit."""

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


def build_slack_blocks(answer: str, sources: list[dict]) -> list[dict]:
    """Create a compact Block Kit card with an answer and citation badges."""
    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": (answer or "I could not generate an answer.")[:_MAX_SECTION_CHARS]}}
    ]
    if sources:
        blocks.append({"type": "header", "text": {"type": "plain_text", "text": "Sources"}})
        for source in sources[:20]:
            title = str(source.get("title", "Untitled")).replace("<", "&lt;").replace(">", "&gt;")
            url = str(source.get("url", ""))
            space = str(source.get("space", "COS40005"))
            citation = f"• *Source:* {title} (Space: `{space}`)"
            if url.startswith(("https://", "http://")):
                citation = f"• *Source:* <{url}|{title}> (Space: `{space}`)"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": citation}})
    return blocks[:50]
