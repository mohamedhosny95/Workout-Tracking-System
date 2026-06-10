from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters

# Stub — full implementation in Step 4
log_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("log", lambda u, c: None)],
    states={},
    fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
)
