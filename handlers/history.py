from telegram import Update

# Stub — full implementation in Step 6
async def history_handler(update: Update, context) -> None:
    await update.message.reply_text("🚧 Coming soon: /history")
