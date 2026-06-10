import logging
import sys
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler
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

COMMANDS = [
    BotCommand("start",        "Welcome message & command list"),
    BotCommand("log",          "Log a workout exercise"),
    BotCommand("template",     "Start a session from a saved template"),
    BotCommand("exercises",    "Browse or search the exercise library"),
    BotCommand("add_exercise", "Add a new exercise to the library"),
    BotCommand("history",      "Last 7 days of logged workouts"),
    BotCommand("summary",      "Weekly stats: volume, sets, muscle groups"),
    BotCommand("cancel",       "Cancel any active flow"),
]


async def post_init(app: Application) -> None:
    """Runs after the bot connects — registers the command menu."""
    await app.bot.set_my_commands(COMMANDS)
    logger.info("Command menu registered.")


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

    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(log_conv_handler)       # ConversationHandler
    app.add_handler(template_conv_handler)  # ConversationHandler
    app.add_handler(add_exercise_handler)   # ConversationHandler
    app.add_handler(exercises_handler)      # CommandHandler
    app.add_handler(history_handler)        # CommandHandler
    app.add_handler(summary_handler)        # CommandHandler

    logger.info("Bot is running.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
