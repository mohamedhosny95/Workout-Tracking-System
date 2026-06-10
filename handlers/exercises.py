from telegram import Update

# Stub — full implementation in Step 5
async def exercises_handler(update: Update, context) -> None:
    await update.message.reply_text("🚧 Coming soon: /exercises")

async def add_exercise_handler(update: Update, context) -> None:
    await update.message.reply_text("🚧 Coming soon: /add_exercise")
