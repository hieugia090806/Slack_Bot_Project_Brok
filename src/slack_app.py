import os
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

# Initialize Slack Bolt App safely
slack_app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
    process_before_response=True
)

slack_handler = SlackRequestHandler(slack_app)

@slack_app.event("app_mention")
def handle_mention(event, say):
    user = event.get("user", "unknown")
    text = event.get("text", "")
    say(f"Hi <@{user}>! I received your query: '{text}'. RAG search pipeline is active.")
