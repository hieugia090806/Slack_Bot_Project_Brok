import os
from fastapi import FastAPI, Request
from src.slack_app import slack_handler

app = FastAPI(title="Slack RAG Bot (Brok)", version="1.0.0")

@app.get("/")
def health_check():
    return {"status": "online", "system": "Brok RAG Backend"}

@app.post("/slack/events")
async def endpoint(req: Request):
    return await slack_handler.handle(req)
