from telegram import Update

# Stub — full implementation in Step 8
async def summary_handler(update: Update, context) -> None:
    await update.message.reply_text("🚧 Coming soon: /summary")
