import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
import notion_service as ns

logger = logging.getLogger(__name__)

# States for /add_exercise
(
    AE_NAME,
    AE_CATEGORY,
    AE_MOVEMENT,
    AE_SETS,
    AE_REPS,
    AE_UNIT,
    AE_COMPOUND,
    AE_CONFIRM,
) = range(8)

_CATEGORIES = ["Strength", "Cardio", "Flexibility", "HIIT", "Mobility", "Olympic"]
_MOVEMENTS = ["Push", "Pull", "Hinge", "Squat", "Carry", "Rotation", "Isolation"]
_UNITS = ["kg", "lbs", "bodyweight"]

_AE = "ae"  # context key — stores in-progress exercise data


# ---------------------------------------------------------------------------
# /exercises — browse and search
# ---------------------------------------------------------------------------

async def exercises_handler(update: Update, context) -> None:
    args = context.args
    if args:
        query = " ".join(args)
        await _search_and_show(update, query)
    else:
        await update.message.reply_text(
            "🔍 Search the exercise library:\n"
            "Type /exercises <name> to search (e.g. /exercises bench)\n"
            "Or type /exercises all to list everything."
        )


async def _search_and_show(update: Update, query: str) -> None:
    try:
        if query.lower() == "all":
            results = ns.get_all_exercises()
            header = f"📚 All exercises ({len(results)} total):"
        else:
            results = ns.search_exercises(query)
            header = f"🔍 Results for *{query}*:"
    except Exception:
        await update.message.reply_text("⚠️ Couldn't reach Notion. Try again.")
        return

    if not results:
        await update.message.reply_text(
            f"No exercises found for *{query}*.\nUse /add\\_exercise to create one.",
            parse_mode="Markdown",
        )
        return

    chunks: list[str] = [header]
    current_chunk: list[str] = []

    for ex in results:
        cat = ex.get("category") or "—"
        pattern = ex.get("movement_pattern") or "—"
        compound = " · Compound" if ex.get("is_compound") else ""
        default_sets = ex.get("default_sets")
        default_reps = ex.get("default_reps")
        default_unit = ex.get("default_unit") or "kg"
        defaults_str = ""
        if default_sets and default_reps:
            defaults_str = f" · {int(default_sets)}×{int(default_reps)} @ {default_unit}"
        entry = (
            f"\n*{ex['name']}*\n"
            f"  {cat} · {pattern}{compound}{defaults_str}"
        )
        current_chunk.append(entry)

        # Send current chunk before hitting Telegram's 4096-char limit
        if sum(len(e) for e in current_chunk) > 3500:
            await update.message.reply_text(
                "\n".join(chunks + current_chunk[:-1]), parse_mode="Markdown"
            )
            chunks = []
            current_chunk = [current_chunk[-1]]

    if current_chunk or chunks:
        await update.message.reply_text(
            "\n".join(chunks + current_chunk), parse_mode="Markdown"
        )


# ---------------------------------------------------------------------------
# /add_exercise — conversation flow
# ---------------------------------------------------------------------------

async def add_exercise_start(update: Update, context) -> int:
    context.user_data[_AE] = {}
    await update.message.reply_text(
        "Let's add a new exercise.\n\nWhat's the *name*?",
        parse_mode="Markdown",
    )
    return AE_NAME


async def ae_name(update: Update, context) -> int:
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Name is too short. Try again.")
        return AE_NAME
    context.user_data[_AE]["name"] = name

    keyboard = [
        [InlineKeyboardButton(c, callback_data=f"ae_cat:{c}")]
        for c in _CATEGORIES
    ]
    keyboard.append([InlineKeyboardButton("Skip", callback_data="ae_cat:skip")])
    await update.message.reply_text(
        "Category?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return AE_CATEGORY


async def ae_category(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    val = query.data.split(":", 1)[1]
    context.user_data[_AE]["category"] = None if val == "skip" else val

    keyboard = [
        [InlineKeyboardButton(m, callback_data=f"ae_mov:{m}")]
        for m in _MOVEMENTS
    ]
    keyboard.append([InlineKeyboardButton("Skip", callback_data="ae_mov:skip")])
    await query.message.reply_text(
        "Movement pattern?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return AE_MOVEMENT


async def ae_movement(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    val = query.data.split(":", 1)[1]
    context.user_data[_AE]["movement_pattern"] = None if val == "skip" else val

    keyboard = [[InlineKeyboardButton("Skip", callback_data="ae_sets:skip")]]
    await query.message.reply_text(
        "Default sets? (type a number or tap Skip)",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return AE_SETS


async def ae_sets_text(update: Update, context) -> int:
    return await _handle_ae_sets(update.message, update.message.text.strip(), context)


async def ae_sets_callback(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    return await _handle_ae_sets(query.message, "skip", context)


async def _handle_ae_sets(message, text: str, context) -> int:
    if text == "skip":
        context.user_data[_AE]["default_sets"] = None
    else:
        try:
            val = int(text)
            if not (1 <= val <= 20):
                raise ValueError
            context.user_data[_AE]["default_sets"] = val
        except ValueError:
            await message.reply_text("Enter a number 1–20, or tap Skip.")
            return AE_SETS

    keyboard = [[InlineKeyboardButton("Skip", callback_data="ae_reps:skip")]]
    await message.reply_text(
        "Default reps? (type a number or tap Skip)",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return AE_REPS


async def ae_reps_text(update: Update, context) -> int:
    return await _handle_ae_reps(update.message, update.message.text.strip(), context)


async def ae_reps_callback(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    return await _handle_ae_reps(query.message, "skip", context)


async def _handle_ae_reps(message, text: str, context) -> int:
    if text == "skip":
        context.user_data[_AE]["default_reps"] = None
    else:
        try:
            val = int(text)
            if not (1 <= val <= 100):
                raise ValueError
            context.user_data[_AE]["default_reps"] = val
        except ValueError:
            await message.reply_text("Enter a number 1–100, or tap Skip.")
            return AE_REPS

    keyboard = [
        [InlineKeyboardButton(u, callback_data=f"ae_unit:{u}") for u in _UNITS]
    ]
    await message.reply_text(
        "Default weight unit?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return AE_UNIT


async def ae_unit(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    context.user_data[_AE]["default_unit"] = query.data.split(":", 1)[1]

    keyboard = [
        [
            InlineKeyboardButton("Yes (compound)", callback_data="ae_comp:yes"),
            InlineKeyboardButton("No (isolation)", callback_data="ae_comp:no"),
        ]
    ]
    await query.message.reply_text(
        "Is this a compound movement? (uses multiple muscle groups)",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return AE_COMPOUND


async def ae_compound(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    context.user_data[_AE]["is_compound"] = query.data == "ae_comp:yes"

    data = context.user_data[_AE]
    sets_str = str(int(data["default_sets"])) if data.get("default_sets") else "—"
    reps_str = str(int(data["default_reps"])) if data.get("default_reps") else "—"
    summary = (
        f"*{data['name']}*\n"
        f"  Category: {data.get('category') or '—'}\n"
        f"  Movement: {data.get('movement_pattern') or '—'}\n"
        f"  Default: {sets_str}×{reps_str} @ {data.get('default_unit') or '—'}\n"
        f"  Compound: {'Yes' if data.get('is_compound') else 'No'}"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Save", callback_data="ae_confirm:yes"),
            InlineKeyboardButton("❌ Cancel", callback_data="ae_confirm:no"),
        ]
    ]
    await query.message.reply_text(
        f"Save this exercise?\n\n{summary}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return AE_CONFIRM


async def ae_confirm(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    if query.data == "ae_confirm:no":
        context.user_data.pop(_AE, None)
        await query.message.reply_text("Cancelled.")
        return ConversationHandler.END

    data = context.user_data[_AE]
    try:
        ns.add_exercise(
            name=data["name"],
            category=data.get("category"),
            muscle_group_ids=[],
            description=None,
            default_sets=data.get("default_sets"),
            default_reps=data.get("default_reps"),
            default_unit=data.get("default_unit"),
            movement_pattern=data.get("movement_pattern"),
            is_compound=data.get("is_compound", False),
        )
    except Exception:
        await query.message.reply_text("⚠️ Couldn't save to Notion. Try again.")
        return AE_CONFIRM

    context.user_data.pop(_AE, None)
    await query.message.reply_text(
        f"✅ *{data['name']}* added to the Exercise Library!",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def ae_cancel(update: Update, context) -> int:
    context.user_data.pop(_AE, None)
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Handler assembly
# ---------------------------------------------------------------------------

exercises_handler = CommandHandler("exercises", exercises_handler)

add_exercise_handler = ConversationHandler(
    entry_points=[CommandHandler("add_exercise", add_exercise_start)],
    states={
        AE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ae_name)],
        AE_CATEGORY: [CallbackQueryHandler(ae_category, pattern=r"^ae_cat:")],
        AE_MOVEMENT: [CallbackQueryHandler(ae_movement, pattern=r"^ae_mov:")],
        AE_SETS: [
            CallbackQueryHandler(ae_sets_callback, pattern=r"^ae_sets:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, ae_sets_text),
        ],
        AE_REPS: [
            CallbackQueryHandler(ae_reps_callback, pattern=r"^ae_reps:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, ae_reps_text),
        ],
        AE_UNIT: [CallbackQueryHandler(ae_unit, pattern=r"^ae_unit:")],
        AE_COMPOUND: [CallbackQueryHandler(ae_compound, pattern=r"^ae_comp:")],
        AE_CONFIRM: [CallbackQueryHandler(ae_confirm, pattern=r"^ae_confirm:")],
    },
    fallbacks=[CommandHandler("cancel", ae_cancel)],
    name="add_exercise",
    persistent=False,
)
