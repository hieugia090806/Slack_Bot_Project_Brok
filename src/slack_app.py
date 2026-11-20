import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

from src.formatter import build_slack_blocks
from src.rag import answer_question
from src.ingestion import ingest_local_docs
from src.vector_store import get_vector_store

logger = logging.getLogger(__name__)
answer_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="brok-answer")
SYNC_INTERVAL = timedelta(hours=3)
_sync_lock = Lock()
_ingestion_lock = Lock()
_last_sync_at: datetime | None = None
_sync_in_progress = False


def run_ingestion_sync(trigger: str = "manual") -> int:
    """Run ingestion and record completion time for lazy-sync gating."""
    global _last_sync_at, _sync_in_progress
    with _sync_lock:
        if _sync_in_progress:
            logger.info("Skipped duplicate %s sync request; a sync is already running", trigger)
            return 0
        _sync_in_progress = True
    try:
        with _ingestion_lock:
            count = ingest_local_docs(trigger=trigger)
        with _sync_lock:
            _last_sync_at = datetime.now(timezone.utc)
        return count
    finally:
        with _sync_lock:
            _sync_in_progress = False


def schedule_startup_sync():
    """Schedule the startup refresh on the shared ingestion worker pool."""
    global _sync_in_progress

    def startup_sync() -> int:
        try:
            count = get_vector_store().document_count
            if count == 0:
                logger.warning("Vector store is empty; starting self-healing Confluence ingestion")
            else:
                logger.info("Vector store contains %d chunks; refreshing from Confluence", count)
        except Exception:
            logger.exception("Could not inspect vector store count before startup sync")
        # Always refresh at startup, which also repairs an empty store and prunes stale pages.
        return _run_claimed_sync(trigger="startup")

    with _sync_lock:
        if _sync_in_progress:
            logger.info("Skipped duplicate startup sync request; a sync is already running")
            return None
        _sync_in_progress = True
    try:
        return answer_pool.submit(startup_sync)
    except RuntimeError:
        with _sync_lock:
            _sync_in_progress = False
        logger.exception("Could not schedule startup Confluence sync")
        return None


def maybe_schedule_lazy_sync() -> None:
    """Schedule at most one automatic sync when the three-hour gate expires."""
    global _sync_in_progress
    now = datetime.now(timezone.utc)
    with _sync_lock:
        if _sync_in_progress or (
            _last_sync_at is not None and now - _last_sync_at < SYNC_INTERVAL
        ):
            return
        _sync_in_progress = True
    try:
        answer_pool.submit(_run_claimed_sync, "lazy")
        logger.info("Scheduled time-gated Confluence sync")
    except RuntimeError:
        with _sync_lock:
            _sync_in_progress = False
        logger.exception("Could not schedule time-gated Confluence sync")


def _run_claimed_sync(trigger: str) -> int:
    """Execute a sync whose in-progress slot was claimed by its scheduler."""
    global _last_sync_at, _sync_in_progress
    try:
        with _ingestion_lock:
            count = ingest_local_docs(trigger=trigger)
        with _sync_lock:
            _last_sync_at = datetime.now(timezone.utc)
        return count
    finally:
        with _sync_lock:
            _sync_in_progress = False


def _reply_sync_claimed(client, channel: str, thread_ts: str) -> None:
    """Reply to a manual sync whose coordinator slot is already claimed."""
    try:
        count = _run_claimed_sync("manual")
        message = f"Confluence sync complete. Indexed {count} chunks."
    except Exception:
        logger.exception("Manual Confluence sync failed")
        message = "Confluence sync failed. Please check the service logs and try again."
    try:
        client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=message)
    except Exception:
        logger.exception("Could not send manual sync status to Slack")


def _is_sync_command(query: str) -> bool:
    return bool(re.search(r"\bsync\b", query, flags=re.IGNORECASE))

# Initialize Slack Bolt App safely
slack_app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
    process_before_response=True
)

slack_handler = SlackRequestHandler(slack_app)


def _reply_to_query(client, channel: str, thread_ts: str, user_id: str, query: str):
    try:
        response = client.users_info(user=user_id)
        user_email = response.get("user", {}).get("profile", {}).get("email") or ""
        logger.info("Slack query identity resolved user_id=%s email_available=%s", user_id, bool(user_email))
    except Exception:
        logger.warning("Could not look up Slack email for %s", user_id, exc_info=True)
        user_email = ""

    try:
        logger.info("Processing Slack query for user_id=%s email_available=%s", user_id, bool(user_email))
        answer = answer_question(query, user_email)
    except Exception:
        logger.exception("Failed to answer Slack query")
        answer = "I could not search the knowledge base right now. Please try again later."

    answer_body = answer.get("answer", "I couldn't generate a response.") if isinstance(answer, dict) else str(answer)
    sources = answer.get("sources", []) if isinstance(answer, dict) else []
    logger.info("Sending Slack response citations=%s", [source.get("url") for source in sources])
    client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=answer_body,
        blocks=build_slack_blocks(answer_body, sources),
    )


def _submit_query(client, event: dict, query: str):
    global _sync_in_progress
    channel = event["channel"]
    thread_ts = event.get("thread_ts") or event["ts"]
    user_id = event.get("user")
    if not user_id or not query:
        return
    if _is_sync_command(query):
        with _sync_lock:
            already_running = _sync_in_progress
            if not already_running:
                _sync_in_progress = True
        if already_running:
            answer_pool.submit(client.chat_postMessage, channel=channel, thread_ts=thread_ts,
                               text="A Confluence sync is already in progress.")
        else:
            try:
                answer_pool.submit(_reply_sync_claimed, client, channel, thread_ts)
            except RuntimeError:
                with _sync_lock:
                    _sync_in_progress = False
                logger.exception("Could not schedule manual Confluence sync")
                answer_pool.submit(client.chat_postMessage, channel=channel, thread_ts=thread_ts,
                                   text="Confluence sync could not be scheduled. Please try again.")
        return
    answer_pool.submit(_reply_to_query, client, channel, thread_ts, user_id, query)


@slack_app.event("app_mention")
def handle_mention(event, client):
    query = re.sub(r"<@[^>]+>", "", event.get("text", "")).strip()
    _submit_query(client, event, query)


@slack_app.message("")
def handle_direct_message(message, client):
    if message.get("channel_type") != "im" or message.get("subtype"):
        return
    _submit_query(client, message, message.get("text", "").strip())
