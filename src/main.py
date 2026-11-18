"""FastAPI host for AIRA-style Slack interaction and health endpoints."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from src.slack_app import maybe_schedule_lazy_sync, schedule_startup_sync, slack_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ingestion_future = schedule_startup_sync()
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
