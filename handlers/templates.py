import logging
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

# States
SELECT_TEMPLATE, TEMPLATE_SETS, TEMPLATE_REPS, TEMPLATE_WEIGHT, TEMPLATE_RPE, TEMPLATE_CONFIRM = range(6)

# context.user_data keys
_SESSION_ID = "tmpl_session_id"
_SESSION_DATE = "tmpl_session_date"
_TEMPLATE = "tmpl_template"
_EXERCISES = "tmpl_exercises"       # list of exercise dicts in order
_CURRENT_IDX = "tmpl_idx"           # which exercise we're on
_SETS = "tmpl_sets"
_REPS = "tmpl_reps"
_WEIGHT = "tmpl_weight"
_UNIT = "tmpl_unit"
_RPE = "tmpl_rpe"


# ---------------------------------------------------------------------------
# Entry — list templates
# ---------------------------------------------------------------------------

async def template_start(update: Update, context) -> int:
    try:
        templates = ns.get_all_templates()
    except Exception:
        await update.message.reply_text("⚠️ Couldn't reach Notion. Try again.")
        return ConversationHandler.END

    if not templates:
        await update.message.reply_text(
            "No templates found.\n"
            "Create one in Notion under *Workout Templates* and link exercises to it.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(_template_label(t), callback_data=f"tmpl:{i}")]
        for i, t in enumerate(templates)
    ]
    context.user_data[_EXERCISES] = templates  # temporarily store to pick from
    await update.message.reply_text(
        "Choose a template:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_TEMPLATE


def _template_label(t: dict) -> str:
    tag = f" [{t['day_tag']}]" if t.get("day_tag") else ""
    focus = f" · {t['training_focus']}" if t.get("training_focus") else ""
    return f"{t['name']}{tag}{focus}"


# ---------------------------------------------------------------------------
# State 0 — pick template
# ---------------------------------------------------------------------------

async def select_template(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    idx = int(query.data.split(":")[1])
    template = context.user_data[_EXERCISES][idx]
    context.user_data[_TEMPLATE] = template

    if not template["exercise_ids"]:
        await query.message.reply_text(
            f"*{template['name']}* has no exercises linked yet.\n"
            "Add exercises to it in Notion first.",
            parse_mode="Markdown",
        )
        _clear_session(context)
        return ConversationHandler.END

    # Fetch all exercises for this template
    try:
        exercises = ns.get_exercises_by_ids(template["exercise_ids"])
    except Exception:
        await query.message.reply_text("⚠️ Couldn't load exercises. Try again.")
        return ConversationHandler.END

    context.user_data[_EXERCISES] = exercises
    context.user_data[_CURRENT_IDX] = 0

    # Create session
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    context.user_data[_SESSION_DATE] = date
    try:
        session_name = f"{template['name']} – {datetime.now(timezone.utc).strftime('%b %d, %Y')}"
        session_id = ns.create_workout_session(
            name=session_name,
            date=date,
            session_type=template.get("training_focus"),
            template_id=template["id"],
        )
        context.user_data[_SESSION_ID] = session_id
    except Exception:
        await query.message.reply_text("⚠️ Couldn't create session in Notion. Try again.")
        return ConversationHandler.END

    notes = template.get("notes")
    notes_str = f"\n_{notes}_" if notes else ""
    total = len(exercises)
    await query.message.reply_text(
        f"Starting *{template['name']}* — {total} exercise{'s' if total != 1 else ''}{notes_str}",
        parse_mode="Markdown",
    )
    return await _prompt_exercise(query.message, context)


# ---------------------------------------------------------------------------
# Exercise prompts (reused for each exercise in the template)
# ---------------------------------------------------------------------------

async def _prompt_exercise(message, context) -> int:
    exercises = context.user_data[_EXERCISES]
    idx = context.user_data[_CURRENT_IDX]
    ex = exercises[idx]
    total = len(exercises)

    default_sets = int(ex.get("default_sets") or 3)
    default_reps = int(ex.get("default_reps") or 8)
    unit = ex.get("default_unit") or "kg"
    context.user_data[_UNIT] = unit

    keyboard = [[InlineKeyboardButton(str(default_sets), callback_data=f"ts:{default_sets}")]]
    await message.reply_text(
        f"*{idx + 1}/{total} — {ex['name']}*\n\nSets? (default: {default_sets})",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return TEMPLATE_SETS


# ---------------------------------------------------------------------------
# Sets
# ---------------------------------------------------------------------------

async def tmpl_sets_text(update: Update, context) -> int:
    return await _handle_tmpl_sets(update.message, update.message.text.strip(), context)


async def tmpl_sets_callback(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    return await _handle_tmpl_sets(query.message, query.data.split(":")[1], context)


async def _handle_tmpl_sets(message, text: str, context) -> int:
    try:
        val = int(text)
        if not (1 <= val <= 20):
            raise ValueError
    except ValueError:
        await message.reply_text("Enter a number 1–20.")
        return TEMPLATE_SETS
    context.user_data[_SETS] = val

    ex = context.user_data[_EXERCISES][context.user_data[_CURRENT_IDX]]
    default_reps = int(ex.get("default_reps") or 8)
    keyboard = [[InlineKeyboardButton(str(default_reps), callback_data=f"tr:{default_reps}")]]
    await message.reply_text(
        f"Reps per set? (default: {default_reps})",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return TEMPLATE_REPS


# ---------------------------------------------------------------------------
# Reps
# ---------------------------------------------------------------------------

async def tmpl_reps_text(update: Update, context) -> int:
    return await _handle_tmpl_reps(update.message, update.message.text.strip(), context)


async def tmpl_reps_callback(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    return await _handle_tmpl_reps(query.message, query.data.split(":")[1], context)


async def _handle_tmpl_reps(message, text: str, context) -> int:
    try:
        val = int(text)
        if not (1 <= val <= 100):
            raise ValueError
    except ValueError:
        await message.reply_text("Enter a number 1–100.")
        return TEMPLATE_REPS
    context.user_data[_REPS] = val

    unit = context.user_data[_UNIT]
    keyboard = [[InlineKeyboardButton("0 (bodyweight)", callback_data="tw:0")]]
    await message.reply_text(
        f"Weight? ({unit}) — type 0 for bodyweight",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return TEMPLATE_WEIGHT


# ---------------------------------------------------------------------------
# Weight
# ---------------------------------------------------------------------------

async def tmpl_weight_text(update: Update, context) -> int:
    return await _handle_tmpl_weight(update.message, update.message.text.strip(), context)


async def tmpl_weight_callback(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    return await _handle_tmpl_weight(query.message, query.data.split(":")[1], context)


async def _handle_tmpl_weight(message, text: str, context) -> int:
    try:
        val = float(text)
        if val < 0:
            raise ValueError
    except ValueError:
        await message.reply_text("Enter a number ≥ 0.")
        return TEMPLATE_WEIGHT
    context.user_data[_WEIGHT] = val

    keyboard = [
        [InlineKeyboardButton("Skip", callback_data="trpe:skip")],
        [InlineKeyboardButton(str(i), callback_data=f"trpe:{i}") for i in range(6, 11)],
    ]
    await message.reply_text(
        "RPE? (1–10) — tap Skip to leave blank.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return TEMPLATE_RPE


# ---------------------------------------------------------------------------
# RPE
# ---------------------------------------------------------------------------

async def tmpl_rpe_text(update: Update, context) -> int:
    return await _handle_tmpl_rpe(update.message, update.message.text.strip(), context)


async def tmpl_rpe_callback(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    return await _handle_tmpl_rpe(query.message, query.data.split(":")[1], context)


async def _handle_tmpl_rpe(message, text: str, context) -> int:
    if text == "skip":
        context.user_data[_RPE] = None
    else:
        try:
            val = float(text)
            if not (1 <= val <= 10):
                raise ValueError
            context.user_data[_RPE] = val
        except ValueError:
            await message.reply_text("Enter 1–10 or tap Skip.")
            return TEMPLATE_RPE

    ex = context.user_data[_EXERCISES][context.user_data[_CURRENT_IDX]]
    sets = context.user_data[_SETS]
    reps = context.user_data[_REPS]
    weight = context.user_data[_WEIGHT]
    unit = context.user_data[_UNIT]
    rpe = context.user_data.get(_RPE)

    weight_str = "bodyweight" if weight == 0 else f"{weight:g}{unit}"
    rpe_str = f" · RPE {rpe:g}" if rpe else ""
    summary = f"*{ex['name']}* — {sets}×{reps} @ {weight_str}{rpe_str}"

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data="tc:yes"),
            InlineKeyboardButton("❌ Redo", callback_data="tc:no"),
        ]
    ]
    await message.reply_text(
        f"Logging:\n{summary}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return TEMPLATE_CONFIRM


# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------

async def tmpl_confirm(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    if query.data == "tc:no":
        # Redo current exercise
        return await _prompt_exercise(query.message, context)

    ex = context.user_data[_EXERCISES][context.user_data[_CURRENT_IDX]]
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
        return TEMPLATE_CONFIRM

    exercises = context.user_data[_EXERCISES]
    idx = context.user_data[_CURRENT_IDX]
    next_idx = idx + 1

    if next_idx >= len(exercises):
        # All done
        try:
            ns.complete_workout_session(context.user_data[_SESSION_ID])
        except Exception:
            pass
        _clear_session(context)
        await query.message.reply_text(
            "✅ Template complete! All exercises logged. Great workout! 💪"
        )
        return ConversationHandler.END

    # Prompt next exercise
    next_ex = exercises[next_idx]
    keyboard = [
        [
            InlineKeyboardButton(f"▶️ Next: {next_ex['name']}", callback_data="tnext:go"),
            InlineKeyboardButton("⏭ Skip", callback_data="tnext:skip"),
            InlineKeyboardButton("🏁 Done", callback_data="tnext:done"),
        ]
    ]
    await query.message.reply_text(
        f"✅ Logged! Up next: *{next_ex['name']}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    context.user_data[_CURRENT_IDX] = next_idx
    return TEMPLATE_CONFIRM


async def tmpl_next(update: Update, context) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    action = query.data.split(":")[1]

    if action == "done":
        try:
            ns.complete_workout_session(context.user_data[_SESSION_ID])
        except Exception:
            pass
        _clear_session(context)
        await query.message.reply_text("Session saved. Well done! 💪")
        return ConversationHandler.END

    if action == "skip":
        exercises = context.user_data[_EXERCISES]
        idx = context.user_data[_CURRENT_IDX]
        next_idx = idx + 1
        if next_idx >= len(exercises):
            try:
                ns.complete_workout_session(context.user_data[_SESSION_ID])
            except Exception:
                pass
            _clear_session(context)
            await query.message.reply_text("Template complete! 💪")
            return ConversationHandler.END
        context.user_data[_CURRENT_IDX] = next_idx

    return await _prompt_exercise(query.message, context)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

async def tmpl_cancel(update: Update, context) -> int:
    _clear_session(context)
    await update.message.reply_text("Template session cancelled.")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_session(context) -> None:
    for key in (_SESSION_ID, _SESSION_DATE, _TEMPLATE, _EXERCISES,
                _CURRENT_IDX, _SETS, _REPS, _WEIGHT, _UNIT, _RPE):
        context.user_data.pop(key, None)


# ---------------------------------------------------------------------------
# Handler assembly
# ---------------------------------------------------------------------------

template_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("template", template_start)],
    states={
        SELECT_TEMPLATE: [
            CallbackQueryHandler(select_template, pattern=r"^tmpl:"),
        ],
        TEMPLATE_SETS: [
            CallbackQueryHandler(tmpl_sets_callback, pattern=r"^ts:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, tmpl_sets_text),
        ],
        TEMPLATE_REPS: [
            CallbackQueryHandler(tmpl_reps_callback, pattern=r"^tr:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, tmpl_reps_text),
        ],
        TEMPLATE_WEIGHT: [
            CallbackQueryHandler(tmpl_weight_callback, pattern=r"^tw:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, tmpl_weight_text),
        ],
        TEMPLATE_RPE: [
            CallbackQueryHandler(tmpl_rpe_callback, pattern=r"^trpe:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, tmpl_rpe_text),
        ],
        TEMPLATE_CONFIRM: [
            CallbackQueryHandler(tmpl_confirm, pattern=r"^tc:"),
            CallbackQueryHandler(tmpl_next, pattern=r"^tnext:"),
        ],
    },
    fallbacks=[CommandHandler("cancel", tmpl_cancel)],
    name="template",
    persistent=False,
)
