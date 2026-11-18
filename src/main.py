"""FastAPI host for AIRA-style Slack interaction and health endpoints."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from src.ingestion import ingest_local_docs
from src.slack_app import maybe_schedule_lazy_sync, slack_handler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def startup_sync() -> None:
        logger.info("Startup Confluence sync started")
        try:
            count = await asyncio.to_thread(ingest_local_docs)
            logger.info("Startup Confluence sync completed; indexed %d chunks", count)
        except Exception:
            logger.exception("Startup Confluence sync failed")

    app.state.ingestion_task = asyncio.create_task(startup_sync(), name="startup-confluence-sync")
    yield


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
    maybe_schedule_lazy_sync()
    return await slack_handler.handle(request)
