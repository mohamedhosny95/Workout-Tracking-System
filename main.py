import logging
import sys
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
)
import config
from handlers.log_workout import log_conv_handler
from handlers.exercises import exercises_handler, add_exercise_handler
from handlers.history import history_handler
from handlers.templates import template_conv_handler
from handlers.summary import summary_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context) -> None:
    text = (
        "💪 *Workout Bot*\n\n"
        "Here's what I can do:\n\n"
        "/log — Log a workout exercise\n"
        "/exercises — Browse or search the exercise library\n"
        "/add\\_exercise — Add a new exercise\n"
        "/template — Start a session from a saved template\n"
        "/history — Last 7 days of workouts\n"
        "/summary — Weekly stats and volume\n"
        "/cancel — Cancel any active flow"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


def main() -> None:
    logger.info("Starting Workout Bot (polling mode)...")

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(log_conv_handler)
    app.add_handler(template_conv_handler)
    app.add_handler(CommandHandler("exercises", exercises_handler))
    app.add_handler(CommandHandler("add_exercise", add_exercise_handler))
    app.add_handler(CommandHandler("history", history_handler))
    app.add_handler(CommandHandler("summary", summary_handler))

    logger.info("Bot is running.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
