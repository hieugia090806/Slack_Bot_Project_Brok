"""FastAPI host for AIRA-style Slack interaction and health endpoints.

Confluence ingestion is scheduled off the event loop so health checks and Slack
event delivery can start before remote indexing completes.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from src.ingestion import ingest_local_docs
from src.slack_app import slack_handler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async def ingest_in_background() -> None:
        logger.info("Background Confluence ingestion started")
        try:
            added = await asyncio.to_thread(ingest_local_docs)
            logger.info("Background Confluence ingestion completed; indexed %d chunks", added)
        except Exception:
            logger.warning("Background Confluence ingestion failed", exc_info=True)

    ingestion_task = asyncio.create_task(ingest_in_background(), name="confluence-ingestion")
    yield
    if not ingestion_task.done():
        ingestion_task.cancel()


app = FastAPI(title="Slack RAG Bot (Brok)", version="1.0.0", lifespan=lifespan)


@app.get("/")
def health_check():
    """Basic process health endpoint."""
    return {"status": "online", "system": "Brok RAG Backend"}


@app.get("/health")
def health():
    """Render health check endpoint."""
    return {"status": "healthy"}


@app.post("/slack/events")
async def slack_events(request: Request):
    """Receive Slack Event Subscriptions and URL verification requests."""
    return await slack_handler.handle(request)
