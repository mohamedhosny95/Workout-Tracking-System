from telegram.ext import ConversationHandler, CommandHandler

# Stub — full implementation in Step 7
template_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("template", lambda u, c: None)],
    states={},
    fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
)
