import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return value


TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
NOTION_API_KEY = _require("NOTION_API_KEY")
NOTION_EXERCISE_LIBRARY_DB_ID = _require("NOTION_EXERCISE_LIBRARY_DB_ID")
NOTION_WORKOUT_TEMPLATES_DB_ID = _require("NOTION_WORKOUT_TEMPLATES_DB_ID")
NOTION_WORKOUT_LOG_DB_ID = _require("NOTION_WORKOUT_LOG_DB_ID")
WEBHOOK_URL = _require("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "8080"))
