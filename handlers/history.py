import logging
from collections import defaultdict
from datetime import datetime

from telegram import Update
from telegram.ext import CommandHandler

import notion_service as ns

logger = logging.getLogger(__name__)


def _fmt_date(date_str: str) -> str:
    """'2025-06-10' → 'Tue Jun 10'"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a %b %-d")
    except Exception:
        return date_str


def _fmt_weight(weight, unit: str) -> str:
    if weight == 0 or unit == "bodyweight":
        return "bodyweight"
    return f"{weight:g}{unit}"


async def history_handler(update: Update, context) -> None:
    await update.message.reply_text("⏳ Fetching your last 7 days…")

    try:
        sessions = ns.get_recent_sessions(days=7)
    except Exception:
        await update.message.reply_text("⚠️ Couldn't reach Notion. Try again.")
        return

    if not sessions:
        await update.message.reply_text(
            "No workouts logged in the last 7 days.\nUse /log to start one!"
        )
        return

    # Fetch exercise logs for each session (batch by session)
    # Build: {session_id: [log, ...]}
    session_logs: dict[str, list] = {}
    exercise_cache: dict[str, str] = {}  # exercise_id → name

    for session in sessions:
        try:
            logs = ns.get_logs_for_session(session["id"])
        except Exception:
            logs = []

        # Resolve exercise names we haven't seen yet
        unknown_ids = [
            log["exercise_id"]
            for log in logs
            if log.get("exercise_id") and log["exercise_id"] not in exercise_cache
        ]
        for eid in unknown_ids:
            try:
                ex_list = ns.get_exercises_by_ids([eid])
                if ex_list:
                    exercise_cache[eid] = ex_list[0]["name"]
            except Exception:
                exercise_cache[eid] = "Unknown"

        session_logs[session["id"]] = logs

    # Build output
    lines = ["📅 *Last 7 days*\n"]

    for session in sessions:
        date_str = session.get("date") or "Unknown date"
        session_type = session.get("type") or ""
        type_tag = f" · {session_type}" if session_type else ""
        lines.append(f"*{_fmt_date(date_str)}{type_tag}*")

        logs = session_logs.get(session["id"], [])
        if not logs:
            lines.append("  _(no exercises logged)_")
        else:
            for log in logs:
                name = exercise_cache.get(log.get("exercise_id") or "", "?")
                sets = int(log["sets"]) if log.get("sets") else "?"
                reps = int(log["reps"]) if log.get("reps") else "?"
                weight = log.get("weight") or 0
                unit = log.get("unit") or "kg"
                rpe = log.get("rpe")
                rpe_str = f" · RPE {rpe:g}" if rpe else ""
                lines.append(
                    f"  {name} — {sets}×{reps} @ {_fmt_weight(weight, unit)}{rpe_str}"
                )
        lines.append("")  # blank line between sessions

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


history_handler = CommandHandler("history", history_handler)
