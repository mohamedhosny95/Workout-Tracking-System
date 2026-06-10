import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import CommandHandler

import notion_service as ns

logger = logging.getLogger(__name__)

MEDALS = ["🥇", "🥈", "🥉"]


async def summary_handler(update: Update, context) -> None:
    await update.message.reply_text("⏳ Calculating your weekly summary…")

    try:
        sessions = ns.get_recent_sessions(days=7)
    except Exception:
        await update.message.reply_text("⚠️ Couldn't reach Notion. Try again.")
        return

    if not sessions:
        await update.message.reply_text(
            "No workouts in the last 7 days.\nUse /log to start one!"
        )
        return

    # Fetch all exercise logs across all sessions in one pass
    all_logs: list[dict] = []
    for session in sessions:
        try:
            logs = ns.get_logs_for_session(session["id"])
            all_logs.extend(logs)
        except Exception:
            pass

    # Resolve unique exercises (id → dict)
    exercise_cache: dict[str, dict] = {}
    for log in all_logs:
        eid = log.get("exercise_id")
        if eid and eid not in exercise_cache:
            try:
                exs = ns.get_exercises_by_ids([eid])
                if exs:
                    exercise_cache[eid] = exs[0]
            except Exception:
                exercise_cache[eid] = {"name": "Unknown", "muscle_group_ids": [], "category": None}

    # Load muscle group names once
    muscle_names: dict[str, str] = {}
    try:
        muscle_names = ns.get_all_muscle_groups()
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # Aggregate stats
    # -----------------------------------------------------------------------
    total_sets = 0
    total_reps = 0
    total_volume_kg = 0.0
    sets_per_muscle: dict[str, int] = defaultdict(int)
    sets_per_category: dict[str, int] = defaultdict(int)
    rpe_values: list[float] = []
    session_types: dict[str, int] = defaultdict(int)

    for log in all_logs:
        sets = int(log.get("sets") or 0)
        reps = int(log.get("reps") or 0)
        weight = float(log.get("weight") or 0)
        unit = log.get("unit") or "kg"
        rpe = log.get("rpe")

        total_sets += sets
        total_reps += reps

        # Volume only counts weighted exercises
        if unit == "kg":
            total_volume_kg += sets * reps * weight
        elif unit == "lbs":
            total_volume_kg += sets * reps * weight * 0.453592

        if rpe:
            rpe_values.append(float(rpe))

        ex = exercise_cache.get(log.get("exercise_id") or "")
        if ex:
            # Muscle group breakdown
            for mid in ex.get("muscle_group_ids") or []:
                name = muscle_names.get(mid) or mid[:8]
                sets_per_muscle[name] += sets

            # Category breakdown
            cat = ex.get("category")
            if cat:
                sets_per_category[cat] += sets

    for session in sessions:
        t = session.get("type")
        if t:
            session_types[t] += 1

    # -----------------------------------------------------------------------
    # Date range label
    # -----------------------------------------------------------------------
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=6)).strftime("%b %d").replace(" 0", " ")
    week_end = now.strftime("%b %d").replace(" 0", " ")

    # -----------------------------------------------------------------------
    # Build message
    # -----------------------------------------------------------------------
    lines = [f"📊 *Weekly Summary ({week_start} – {week_end})*\n"]

    lines.append(f"🗓 Sessions: *{len(sessions)}*")
    lines.append(f"📦 Total sets: *{total_sets}*")
    lines.append(f"🔁 Total reps: *{total_reps}*")

    if total_volume_kg > 0:
        lines.append(f"⚖️ Total volume: *{total_volume_kg:,.0f} kg*")

    if rpe_values:
        avg_rpe = sum(rpe_values) / len(rpe_values)
        lines.append(f"🌡 Avg RPE: *{avg_rpe:.1f}*")

    # Session type breakdown
    if session_types:
        lines.append("\n💪 *Session types:*")
        for stype, count in sorted(session_types.items(), key=lambda x: -x[1]):
            lines.append(f"  {stype}: {count}")

    # Top muscle groups
    if sets_per_muscle:
        lines.append("\n🏋️ *Top muscle groups:*")
        top = sorted(sets_per_muscle.items(), key=lambda x: -x[1])[:5]
        for i, (muscle, sets) in enumerate(top):
            medal = MEDALS[i] if i < len(MEDALS) else "  "
            lines.append(f"  {medal} {muscle} — {sets} sets")

    # Category breakdown
    if sets_per_category:
        lines.append("\n📁 *By category:*")
        for cat, sets in sorted(sets_per_category.items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}: {sets} sets")

    # Consistency note
    if len(sessions) >= 5:
        lines.append("\n🔥 *Excellent consistency this week!*")
    elif len(sessions) >= 3:
        lines.append("\n✅ *Solid week — keep it up!*")
    else:
        lines.append("\n💡 _Aim for 3–5 sessions next week._")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


summary_handler = CommandHandler("summary", summary_handler)
