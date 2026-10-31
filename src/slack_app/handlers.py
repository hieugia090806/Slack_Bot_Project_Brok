"""Event handlers. The RAG call is a stub until the rag/ package lands."""
from src.security.whitelist import is_allowed


def answer_stub(question: str) -> str:
    return f"(RAG not connected yet) You asked: {question}"


def register(app, allowed_channels: set[str]) -> None:
    @app.event("app_mention")
    def on_mention(event, say, client):
        channel = event["channel"]
        if not is_allowed(channel, allowed_channels):
            return  # ignore silently
        thread_ts = event.get("thread_ts") or event["ts"]
        placeholder = say(text="Searching...", thread_ts=thread_ts)
        question = event.get("text", "").split(">", 1)[-1].strip()
        client.chat_update(
            channel=channel, ts=placeholder["ts"], text=answer_stub(question)
        )
