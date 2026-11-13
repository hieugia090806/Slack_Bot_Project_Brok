import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from src.slack_app import slack_handler   # We need the SlackRequestHandler, not just the App
from src.ingestion import ingest_confluence_docs

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        added = ingest_confluence_docs()
        logger.info("Startup Confluence ingestion indexed %d chunks", added)
    except Exception:
        # Keep service startup available during a temporary remote dependency outage.
        # No local documents are substituted.
        logger.exception("Startup Confluence ingestion failed")
    yield


app = FastAPI(title="Slack RAG Bot (Brok)", version="1.0.0", lifespan=lifespan)


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
