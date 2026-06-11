import logging
import uuid
from datetime import datetime, timezone

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

# Conversation states
SEARCH_EXERCISE, SELECT_EXERCISE, SETS, REPS, WEIGHT, RPE, CONFIRM = range(7)

# context.user_data keys
_RESULTS = "log_results"
_LIST_PAGE = "log_list_page"
_PENDING_NAME = "log_pending_name"
_EXERCISE = "log_exercise"
_SETS = "log_sets"
_REPS = "log_reps"
_WEIGHT = "log_weight"
_UNIT = "log_unit"
_RPE = "log_rpe"
_SESSION_ID = "log_session_id"
_SESSION_DATE = "log_session_date"

_PAGE_SIZE = 20


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

async def log_start(update: Update, context) -> int:
    # Create a Workout Session page on first exercise of the session
    if _SESSION_ID not in context.user_data:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        context.user_data[_SESSION_DATE] = date
        try:
            session_name = f"Workout – {datetime.now(timezone.utc).strftime('%b %d, %Y')}"
            session_id = ns.create_workout_session(name=session_name, date=date)
            context.user_data[_SESSION_ID] = session_id
        except Exception:
            await update.message.reply_text(
                "⚠️ Couldn't reach Notion. Try again in a moment."
            )
            return ConversationHandler.END

    await update.message.reply_text(
        "Which exercise? Type a name to search, or /list to browse all."
    )
    return SEARCH_EXERCISE


# ---------------------------------------------------------------------------
# State 0 — search
# ---------------------------------------------------------------------------

async def search_exercise(update: Update, context) -> int:
    query = update.message.text.strip()
    try:
        if len(query) <= 2:
            all_ex = ns.get_all_exercises()
            q_lower = query.lower()
            results = [e for e in all_ex if q_lower in e["name"].lower()]
        else:
            results = ns.search_exercises(query)
    except Exception:
        await update.message.reply_text("⚠️ Couldn't reach Notion. Try again.")
        return SEARCH_EXERCISE

    if not results:
        context.user_data[_PENDING_NAME] = query
        keyboard = [
            [
                InlineKeyboardButton(f"➕ Create & log \"{query}\"", callback_data="quickadd:yes"),
                InlineKeyboardButton("🔍 Try again", callback_data="quickadd:no"),
            ]
        ]
        await update.message.reply_text(
            f"No exercises found for *{query}*.\nCreate it now and log it straight away?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SELECT_EXERCISE

    if len(results) == 1:
        context.user_data[_EXERCISE] = results[0]
        return await ask_sets(update, context)

    # 2–10 results — show inline keyboard
    results = results[:10]
    context.user_data[_RESULTS] = results
    keyboard = [
        [InlineKeyboardButton(r["name"], callback_data=str(i))]
        for i, r in enumerate(results)
    ]
    await update.message.reply_text(
        "Found a few matches — pick one:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_EXERCISE


async def list_all(update: Update, context) -> int:
    try:
        all_results = ns.get_all_exercises()
    except Exception:
        await update.message.reply_text("⚠️ Couldn't reach Notion. Try again.")
        return SEARCH_EXERCISE

    if not all_results:
        await update.message.reply_text("No exercises in the library yet. Use /add_exercise to create one.")
        return SEARCH_EXERCISE

    context.user_data[_RESULTS] = all_results
    context.user_data[_LIST_PAGE] = 0
    return await _show_list_page(update.message, context)


async def _show_list_page(message, context) -> int:
    all_results = context.user_data[_RESULTS]
    page = context.user_data.get(_LIST_PAGE, 0)
    total = len(all_results)
    start = page * _PAGE_SIZE
    end = min(start + _PAGE_SIZE, total)
    page_results = all_results[start:end]

    keyboard = [
        [InlineKeyboardButton(r["name"], callback_data=str(start + i))]
        for i, r in enumerate(page_results)
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("➡️ Next", callback_data=f"page:{page + 1}"))
    if nav:
        keyboard.append(nav)

    await message.reply_text(
        f"Exercise library — page {page + 1} of {-(-total // _PAGE_SIZE)} ({total} total):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_EXERCISE


async def list_page_callback(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    page = int(query.data.split(":")[1])
    context.user_data[_LIST_PAGE] = page
    return await _show_list_page(query.message, context)


async def quickadd_callback(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    if query.data == "quickadd:no":
        context.user_data.pop(_PENDING_NAME, None)
        await query.message.reply_text("OK — type a name to search again.")
        return SEARCH_EXERCISE

    name = context.user_data.pop(_PENDING_NAME, None)
    if not name:
        await query.message.reply_text("Something went wrong. Type a name to search again.")
        return SEARCH_EXERCISE

    try:
        ex_id = ns.add_exercise(
            name=name,
            category=None,
            muscle_group_ids=[],
            description=None,
            default_sets=None,
            default_reps=None,
            default_unit="kg",
        )
    except Exception:
        await query.message.reply_text("⚠️ Couldn't save to Notion. Try again.")
        return SEARCH_EXERCISE

    # Fetch the newly created exercise so we have all its fields
    try:
        exs = ns.get_exercises_by_ids([ex_id])
        exercise = exs[0] if exs else {"id": ex_id, "name": name}
    except Exception:
        exercise = {"id": ex_id, "name": name}

    context.user_data[_EXERCISE] = exercise
    await query.message.reply_text(f"✅ *{name}* added to the library!", parse_mode="Markdown")
    return await ask_sets(query.message, context)


# ---------------------------------------------------------------------------
# State 1 — select from keyboard
# ---------------------------------------------------------------------------

async def select_exercise(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    idx = int(query.data)
    results = context.user_data.get(_RESULTS, [])
    if idx < 0 or idx >= len(results):
        await query.message.reply_text("Selection expired. Please search again.")
        return SEARCH_EXERCISE
    exercise = results[idx]
    context.user_data[_EXERCISE] = exercise
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"Selected: *{exercise['name']}*", parse_mode="Markdown")
    return await ask_sets(query.message, context)


# ---------------------------------------------------------------------------
# State 2 — sets
# ---------------------------------------------------------------------------

async def ask_sets(message, context) -> int:
    exercise = context.user_data[_EXERCISE]
    default = int(exercise.get("default_sets") or 3)
    keyboard = [[InlineKeyboardButton(str(default), callback_data=f"sets:{default}")]]
    await message.reply_text(
        f"Sets? (default: {default})",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SETS


async def receive_sets_text(update: Update, context) -> int:
    return await _handle_sets(update.message, update.message.text.strip(), context)


async def receive_sets_callback(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    value = query.data.split(":")[1]
    return await _handle_sets(query.message, value, context)


async def _handle_sets(message, text: str, context) -> int:
    try:
        val = int(text)
        if not (1 <= val <= 20):
            raise ValueError
    except ValueError:
        await message.reply_text("Please enter a whole number between 1 and 20.")
        return SETS
    context.user_data[_SETS] = val
    return await ask_reps(message, context)


# ---------------------------------------------------------------------------
# State 3 — reps
# ---------------------------------------------------------------------------

async def ask_reps(message, context) -> int:
    exercise = context.user_data[_EXERCISE]
    default = int(exercise.get("default_reps") or 8)
    keyboard = [[InlineKeyboardButton(str(default), callback_data=f"reps:{default}")]]
    await message.reply_text(
        f"Reps per set? (default: {default})",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return REPS


async def receive_reps_text(update: Update, context) -> int:
    return await _handle_reps(update.message, update.message.text.strip(), context)


async def receive_reps_callback(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    value = query.data.split(":")[1]
    return await _handle_reps(query.message, value, context)


async def _handle_reps(message, text: str, context) -> int:
    try:
        val = int(text)
        if not (1 <= val <= 100):
            raise ValueError
    except ValueError:
        await message.reply_text("Please enter a whole number between 1 and 100.")
        return REPS
    context.user_data[_REPS] = val
    return await ask_weight(message, context)


# ---------------------------------------------------------------------------
# State 4 — weight
# ---------------------------------------------------------------------------

async def ask_weight(message, context) -> int:
    exercise = context.user_data[_EXERCISE]
    unit = exercise.get("default_unit") or "kg"
    context.user_data[_UNIT] = unit
    keyboard = [[InlineKeyboardButton("0 (bodyweight)", callback_data="weight:0")]]
    await message.reply_text(
        f"Weight? ({unit}) — type 0 for bodyweight",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return WEIGHT


async def receive_weight_text(update: Update, context) -> int:
    return await _handle_weight(update.message, update.message.text.strip(), context)


async def receive_weight_callback(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    value = query.data.split(":")[1]
    return await _handle_weight(query.message, value, context)


async def _handle_weight(message, text: str, context) -> int:
    try:
        val = float(text)
        if val < 0:
            raise ValueError
    except ValueError:
        await message.reply_text("Please enter a number ≥ 0 (e.g. 80 or 0 for bodyweight).")
        return WEIGHT
    context.user_data[_WEIGHT] = val
    return await ask_rpe(message, context)


# ---------------------------------------------------------------------------
# State 5 — RPE (optional)
# ---------------------------------------------------------------------------

async def ask_rpe(message, context) -> int:
    keyboard = [
        [
            InlineKeyboardButton("Skip", callback_data="rpe:skip"),
        ],
        [
            InlineKeyboardButton(str(i), callback_data=f"rpe:{i}")
            for i in range(6, 11)
        ],
    ]
    await message.reply_text(
        "RPE? (Rate of Perceived Exertion, 1–10) — how hard was that set?\nTap Skip to leave blank.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return RPE


async def receive_rpe_text(update: Update, context) -> int:
    return await _handle_rpe(update.message, update.message.text.strip(), context)


async def receive_rpe_callback(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    value = query.data.split(":")[1]
    return await _handle_rpe(query.message, value, context)


async def _handle_rpe(message, text: str, context) -> int:
    if text == "skip":
        context.user_data[_RPE] = None
    else:
        try:
            val = float(text)
            if not (1 <= val <= 10):
                raise ValueError
        except ValueError:
            await message.reply_text("Please enter a number between 1 and 10, or tap Skip.")
            return RPE
        context.user_data[_RPE] = val
    return await show_confirm(message, context)


# ---------------------------------------------------------------------------
# State 6 — confirm
# ---------------------------------------------------------------------------

async def show_confirm(message, context) -> int:
    ex = context.user_data[_EXERCISE]
    sets = context.user_data[_SETS]
    reps = context.user_data[_REPS]
    weight = context.user_data[_WEIGHT]
    unit = context.user_data[_UNIT]
    rpe = context.user_data.get(_RPE)

    weight_str = "bodyweight" if weight == 0 else f"{weight:g}{unit}"
    rpe_str = f" · RPE {rpe}" if rpe else ""
    summary = f"*{ex['name']}* — {sets}×{reps} @ {weight_str}{rpe_str}"

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data="confirm:yes"),
            InlineKeyboardButton("❌ Redo", callback_data="confirm:no"),
        ]
    ]
    await message.reply_text(
        f"Logging:\n{summary}\n\nConfirm?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CONFIRM


async def handle_confirm(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    if query.data == "confirm:no":
        await query.message.reply_text("No problem — let's redo. Which exercise?")
        _clear_entry(context)
        return SEARCH_EXERCISE

    # Write to Notion
    ex = context.user_data[_EXERCISE]
    try:
        ns.log_exercise_entry(
            session_page_id=context.user_data[_SESSION_ID],
            exercise_id=ex["id"],
            sets=context.user_data[_SETS],
            reps=context.user_data[_REPS],
            weight=context.user_data[_WEIGHT],
            unit=context.user_data[_UNIT],
            date=context.user_data[_SESSION_DATE],
            rpe=context.user_data.get(_RPE),
        )
    except Exception:
        await query.message.reply_text("⚠️ Couldn't save to Notion. Try again.")
        return CONFIRM

    _clear_entry(context)

    keyboard = [
        [
            InlineKeyboardButton("➕ Log another", callback_data="next:more"),
            InlineKeyboardButton("✅ Done", callback_data="next:done"),
        ]
    ]
    await query.message.reply_text(
        "✅ Logged! Log another exercise?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CONFIRM


async def handle_next(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    if query.data == "next:done":
        # Mark session complete
        try:
            ns.complete_workout_session(context.user_data[_SESSION_ID])
        except Exception:
            pass
        _clear_session(context)
        await query.message.reply_text("Great workout! Session saved to Notion. 💪")
        return ConversationHandler.END

    await query.message.reply_text("Which exercise? Type a name to search, or /list to browse all.")
    return SEARCH_EXERCISE


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

async def cancel(update: Update, context) -> int:
    _clear_session(context)
    await update.message.reply_text("Cancelled. Type /log to start a new session.")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_entry(context) -> None:
    for key in (_RESULTS, _LIST_PAGE, _PENDING_NAME, _EXERCISE, _SETS, _REPS, _WEIGHT, _UNIT, _RPE):
        context.user_data.pop(key, None)


def _clear_session(context) -> None:
    _clear_entry(context)
    for key in (_SESSION_ID, _SESSION_DATE):
        context.user_data.pop(key, None)


# ---------------------------------------------------------------------------
# Handler assembly
# ---------------------------------------------------------------------------

log_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("log", log_start)],
    states={
        SEARCH_EXERCISE: [
            CommandHandler("list", list_all),
            MessageHandler(filters.TEXT & ~filters.COMMAND, search_exercise),
        ],
        SELECT_EXERCISE: [
            CallbackQueryHandler(quickadd_callback, pattern=r"^quickadd:"),
            CallbackQueryHandler(list_page_callback, pattern=r"^page:"),
            CallbackQueryHandler(select_exercise, pattern=r"^\d+$"),
        ],
        SETS: [
            CallbackQueryHandler(receive_sets_callback, pattern=r"^sets:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_sets_text),
        ],
        REPS: [
            CallbackQueryHandler(receive_reps_callback, pattern=r"^reps:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reps_text),
        ],
        WEIGHT: [
            CallbackQueryHandler(receive_weight_callback, pattern=r"^weight:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_weight_text),
        ],
        RPE: [
            CallbackQueryHandler(receive_rpe_callback, pattern=r"^rpe:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rpe_text),
        ],
        CONFIRM: [
            CallbackQueryHandler(handle_confirm, pattern=r"^confirm:"),
            CallbackQueryHandler(handle_next, pattern=r"^next:"),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    name="log_workout",
    persistent=False,
)
