import os
import threading
from fastapi import FastAPI
from src.slack_app import slack_app
from slack_bolt.adapter.socket_mode import SocketModeHandler

app = FastAPI(title="Slack RAG Bot (Brok)", version="1.0.0")

@app.get("/")
def health_check():
    return {"status": "online", "system": "Brok RAG Backend"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# Start Socket Mode in a background thread when FastAPI boots up, 
# so it doesn't block the Uvicorn web server on Fly.io
@app.on_event("startup")
def start_socket_mode():
    app_token = os.environ.get("SLACK_APP_TOKEN")
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    if app_token and bot_token:
        handler = SocketModeHandler(slack_app, app_token)
        # Run in background thread so Uvicorn can still bind to PORT 8080 for Fly.io
        threading.Thread(target=handler.start, daemon=True).start()