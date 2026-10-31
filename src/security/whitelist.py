"""Channel whitelist. Unknown channels are ignored silently (team design proposal)."""
import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "whitelist.json"


def load_allowed_channels(path: Path = DEFAULT_PATH) -> set[str]:
    with open(path, encoding="utf-8") as f:
        return set(json.load(f).get("allowed_channel_ids", []))


def is_allowed(channel_id: str, allowed: set[str]) -> bool:
    return channel_id in allowed
