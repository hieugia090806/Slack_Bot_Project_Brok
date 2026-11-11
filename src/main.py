import os
import logging
from fastapi import FastAPI, Request
from src.slack_app import slack_handler   # We need the SlackRequestHandler, not just the App

logger = logging.getLogger(__name__)

app = FastAPI(title="Slack RAG Bot (Brok)", version="1.0.0")


@app.get("/")
def health_check():
    return {"status": "online", "system": "Brok RAG Backend"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/slack/events")
async def slack_events(request: Request):
    """
    This is the endpoint Slack will call for Event Subscriptions.
    It must correctly respond to the URL verification challenge.
    """
    return await slack_handler.handle(request)