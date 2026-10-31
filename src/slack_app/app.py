"""Entry point: python -m src.slack_app.app"""
import os

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.security.whitelist import load_allowed_channels
from src.slack_app.handlers import register


def create_app(token: str | None = None, **kwargs) -> App:
    app = App(token=token or os.environ["SLACK_BOT_TOKEN"], **kwargs)
    register(app, load_allowed_channels())
    return app


if __name__ == "__main__":
    load_dotenv()
    SocketModeHandler(create_app(), os.environ["SLACK_APP_TOKEN"]).start()
