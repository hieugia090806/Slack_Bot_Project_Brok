import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

from src.formatter import build_slack_blocks
from src.rag import answer_question

logger = logging.getLogger(__name__)
answer_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="brok-answer")

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
    channel = event["channel"]
    thread_ts = event.get("thread_ts") or event["ts"]
    user_id = event.get("user")
    if not user_id or not query:
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
