import logging
from datetime import datetime, timedelta, timezone
from notion_client import Client
from notion_client.errors import APIResponseError
import config

logger = logging.getLogger(__name__)

_notion = Client(auth=config.NOTION_API_KEY)

# Internal DB — Muscle Group lookup (not in config, it's a fixed existing DB)
_MUSCLE_GROUP_DB_ID = "285fa9ca-b092-8159-97c0-ccfdc149b3f9"

_muscle_group_cache: dict[str, str] = {}  # {page_id: name}


# ---------------------------------------------------------------------------
# Property helpers
# ---------------------------------------------------------------------------

def _title_text(page: dict, prop: str = "Name") -> str:
    parts = page["properties"].get(prop, {}).get("title", [])
    return parts[0]["plain_text"] if parts else ""


def _select(page: dict, prop: str) -> str | None:
    s = page["properties"].get(prop, {}).get("select")
    return s["name"] if s else None


def _number(page: dict, prop: str) -> float | None:
    return page["properties"].get(prop, {}).get("number")


def _rich_text(page: dict, prop: str) -> str | None:
    parts = page["properties"].get(prop, {}).get("rich_text", [])
    return parts[0]["plain_text"] if parts else None


def _date_start(page: dict, prop: str) -> str | None:
    d = page["properties"].get(prop, {}).get("date")
    return d["start"] if d else None


def _relation_ids(page: dict, prop: str) -> list[str]:
    return [r["id"] for r in page["properties"].get(prop, {}).get("relation", [])]


def _checkbox(page: dict, prop: str) -> bool:
    return page["properties"].get(prop, {}).get("checkbox", False)


def _paginate(fn, **kwargs) -> list[dict]:
    """Exhaust all Notion pagination for a databases.query call."""
    results = []
    cursor = None
    while True:
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = fn(**kwargs)
        results.extend(resp["results"])
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    return results


# ---------------------------------------------------------------------------
# Exercise Library
# ---------------------------------------------------------------------------

def search_exercises(query: str) -> list[dict]:
    """Search Exercise Library where Name contains query (case-insensitive)."""
    try:
        pages = _paginate(
            _notion.databases.query,
            database_id=config.NOTION_EXERCISE_LIBRARY_DB_ID,
            filter={"property": "Name", "title": {"contains": query}},
        )
        return [_parse_exercise(p) for p in pages]
    except APIResponseError as e:
        logger.error("search_exercises failed: %s", e)
        raise


def get_all_exercises() -> list[dict]:
    """Full Exercise Library sorted by name."""
    try:
        pages = _paginate(
            _notion.databases.query,
            database_id=config.NOTION_EXERCISE_LIBRARY_DB_ID,
            sorts=[{"property": "Name", "direction": "ascending"}],
        )
        return [_parse_exercise(p) for p in pages]
    except APIResponseError as e:
        logger.error("get_all_exercises failed: %s", e)
        raise


def add_exercise(
    name: str,
    category: str | None,
    muscle_group_ids: list[str],
    description: str | None,
    default_sets: int | None,
    default_reps: int | None,
    default_unit: str | None,
    movement_pattern: str | None = None,
    is_compound: bool = False,
) -> str:
    """Create entry in Exercise Library, return new page ID."""
    try:
        props: dict = {
            "Name": {"title": [{"text": {"content": name}}]},
            "Is Compound": {"checkbox": is_compound},
        }
        if category:
            props["Category"] = {"select": {"name": category}}
        if movement_pattern:
            props["Movement Pattern"] = {"select": {"name": movement_pattern}}
        if muscle_group_ids:
            props["Muscle Group"] = {"relation": [{"id": mid} for mid in muscle_group_ids]}
        if description:
            props["Notes"] = {"rich_text": [{"text": {"content": description}}]}
        if default_sets is not None:
            props["Default Sets"] = {"number": default_sets}
        if default_reps is not None:
            props["Default Reps"] = {"number": default_reps}
        if default_unit:
            props["Default Weight Unit"] = {"select": {"name": default_unit}}

        page = _notion.pages.create(
            parent={"database_id": config.NOTION_EXERCISE_LIBRARY_DB_ID},
            properties=props,
        )
        return page["id"]
    except APIResponseError as e:
        logger.error("add_exercise failed: %s", e)
        raise


def _parse_exercise(page: dict) -> dict:
    return {
        "id": page["id"],
        "name": _title_text(page, "Name"),
        "category": _select(page, "Category"),
        "muscle_group_ids": _relation_ids(page, "Muscle Group"),
        "difficulty": _select(page, "Difficulty"),
        "movement_pattern": _select(page, "Movement Pattern"),
        "default_sets": _number(page, "Default Sets"),
        "default_reps": _number(page, "Default Reps"),
        "default_unit": _select(page, "Default Weight Unit") or "kg",
        "is_compound": _checkbox(page, "Is Compound"),
        "notes": _rich_text(page, "Notes"),
    }


def get_exercises_by_ids(exercise_ids: list[str]) -> list[dict]:
    """Fetch multiple exercises by page ID (used by template handler)."""
    results = []
    for eid in exercise_ids:
        try:
            page = _notion.pages.retrieve(eid)
            results.append(_parse_exercise(page))
        except APIResponseError as e:
            logger.error("get_exercises_by_ids failed for %s: %s", eid, e)
            raise
    return results


# ---------------------------------------------------------------------------
# Muscle Groups
# ---------------------------------------------------------------------------

def get_all_muscle_groups() -> dict[str, str]:
    """Return {page_id: name} for all muscle groups. Cached after first call."""
    global _muscle_group_cache
    if _muscle_group_cache:
        return _muscle_group_cache
    try:
        pages = _paginate(
            _notion.databases.query,
            database_id=_MUSCLE_GROUP_DB_ID,
        )
        _muscle_group_cache = {p["id"]: _title_text(p, "Name") for p in pages}
        return _muscle_group_cache
    except APIResponseError as e:
        logger.error("get_all_muscle_groups failed: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Workout Sessions
# ---------------------------------------------------------------------------

def create_workout_session(
    name: str,
    date: str,
    session_type: str | None = None,
    template_id: str | None = None,
) -> str:
    """Create a new Workout Session page and return its ID."""
    try:
        props: dict = {
            "Name": {"title": [{"text": {"content": name}}]},
            "Date": {"date": {"start": date}},
        }
        if session_type:
            props["Type"] = {"select": {"name": session_type}}
        if template_id:
            props["Template"] = {"relation": [{"id": template_id}]}

        page = _notion.pages.create(
            parent={"database_id": config.NOTION_WORKOUT_SESSION_DB_ID},
            properties=props,
        )
        return page["id"]
    except APIResponseError as e:
        logger.error("create_workout_session failed: %s", e)
        raise


def complete_workout_session(session_page_id: str) -> None:
    """Mark a Workout Session as Done."""
    try:
        _notion.pages.update(
            page_id=session_page_id,
            properties={"Done": {"checkbox": True}},
        )
    except APIResponseError as e:
        logger.error("complete_workout_session failed: %s", e)
        raise


def get_recent_sessions(days: int = 7) -> list[dict]:
    """Return Workout Sessions from last N days, sorted by Date desc."""
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        pages = _paginate(
            _notion.databases.query,
            database_id=config.NOTION_WORKOUT_SESSION_DB_ID,
            filter={"property": "Date", "date": {"on_or_after": since}},
            sorts=[{"property": "Date", "direction": "descending"}],
        )
        return [_parse_session(p) for p in pages]
    except APIResponseError as e:
        logger.error("get_recent_sessions failed: %s", e)
        raise


def _parse_session(page: dict) -> dict:
    return {
        "id": page["id"],
        "name": _title_text(page, "Name"),
        "date": _date_start(page, "Date"),
        "type": _select(page, "Type"),
        "mood": _select(page, "Mood"),
        "done": _checkbox(page, "Done"),
        "exercise_log_ids": _relation_ids(page, "Exercise Logs"),
        "template_ids": _relation_ids(page, "Template"),
        "calories": _number(page, "Calories Burnt"),
        "body_weight": _number(page, "Body Weight (kg)"),
    }


# ---------------------------------------------------------------------------
# Exercise Logs
# ---------------------------------------------------------------------------

def log_exercise_entry(
    session_page_id: str,
    exercise_id: str,
    sets: int,
    reps: int,
    weight: float,
    unit: str,
    date: str,
    rpe: float | None = None,
    rest_sec: int | None = None,
    duration_min: float | None = None,
    notes: str | None = None,
) -> str:
    """Create an Exercise Log entry linked to a Workout Session. Returns page ID."""
    try:
        exercise_page = _notion.pages.retrieve(exercise_id)
        exercise_name = _title_text(exercise_page, "Name")
        entry_label = f"{exercise_name} – {date}"

        props: dict = {
            "Entry Label": {"title": [{"text": {"content": entry_label}}]},
            "Exercise Library": {"relation": [{"id": exercise_id}]},
            "Workout": {"relation": [{"id": session_page_id}]},
            "Sets": {"number": sets},
            "Reps": {"number": reps},
            "Weight": {"number": weight},
            "Weight Unit": {"select": {"name": unit}},
        }
        if rpe is not None:
            props["RPE"] = {"number": rpe}
        if rest_sec is not None:
            props["Rest (sec)"] = {"number": rest_sec}
        if duration_min is not None:
            props["Duration (min)"] = {"number": duration_min}
        if notes:
            props["Notes"] = {"rich_text": [{"text": {"content": notes}}]}

        page = _notion.pages.create(
            parent={"database_id": config.NOTION_EXERCISE_LOGS_DB_ID},
            properties=props,
        )
        return page["id"]
    except APIResponseError as e:
        logger.error("log_exercise_entry failed: %s", e)
        raise


def get_logs_for_session(session_page_id: str) -> list[dict]:
    """Fetch all Exercise Log entries for a given Workout Session."""
    try:
        pages = _paginate(
            _notion.databases.query,
            database_id=config.NOTION_EXERCISE_LOGS_DB_ID,
            filter={"property": "Workout", "relation": {"contains": session_page_id}},
        )
        return [_parse_log_entry(p) for p in pages]
    except APIResponseError as e:
        logger.error("get_logs_for_session failed: %s", e)
        raise


def get_recent_logs(days: int = 7) -> list[dict]:
    """Return Exercise Log entries from last N days via Date rollup."""
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        pages = _paginate(
            _notion.databases.query,
            database_id=config.NOTION_EXERCISE_LOGS_DB_ID,
            filter={"property": "Date", "date": {"on_or_after": since}},
            sorts=[{"property": "Date", "direction": "descending"}],
        )
        return [_parse_log_entry(p) for p in pages]
    except APIResponseError as e:
        logger.error("get_recent_logs failed: %s", e)
        raise


def _parse_log_entry(page: dict) -> dict:
    exercise_ids = _relation_ids(page, "Exercise Library")
    session_ids = _relation_ids(page, "Workout")
    rollup_prop = page["properties"].get("Date", {})
    rollup_date = rollup_prop.get("rollup", {}) if isinstance(rollup_prop, dict) else {}
    date_val = None
    if isinstance(rollup_date, dict) and rollup_date.get("type") == "date":
        date_obj = rollup_date.get("date")
        if isinstance(date_obj, dict):
            date_val = date_obj.get("start")

    return {
        "id": page["id"],
        "label": _title_text(page, "Entry Label"),
        "date": date_val,
        "exercise_id": exercise_ids[0] if exercise_ids else None,
        "session_id": session_ids[0] if session_ids else None,
        "sets": _number(page, "Sets"),
        "reps": _number(page, "Reps"),
        "weight": _number(page, "Weight"),
        "unit": _select(page, "Weight Unit") or "kg",
        "rpe": _number(page, "RPE"),
        "rest_sec": _number(page, "Rest (sec)"),
        "duration_min": _number(page, "Duration (min)"),
        "notes": _rich_text(page, "Notes"),
    }


# ---------------------------------------------------------------------------
# Workout Templates
# ---------------------------------------------------------------------------

def get_all_templates() -> list[dict]:
    """Return all Workout Templates with linked exercise IDs."""
    try:
        pages = _paginate(
            _notion.databases.query,
            database_id=config.NOTION_WORKOUT_TEMPLATES_DB_ID,
            sorts=[{"property": "Name", "direction": "ascending"}],
        )
        return [_parse_template(p) for p in pages]
    except APIResponseError as e:
        logger.error("get_all_templates failed: %s", e)
        raise


def _parse_template(page: dict) -> dict:
    return {
        "id": page["id"],
        "name": _title_text(page, "Name"),
        "day_tag": _select(page, "Day Tag"),
        "training_focus": _select(page, "Training Focus"),
        "target_duration": _number(page, "Target Duration (min)"),
        "notes": _rich_text(page, "Notes"),
        "exercise_ids": _relation_ids(page, "Exercises"),
    }


# ---------------------------------------------------------------------------
# Personal Records
# ---------------------------------------------------------------------------

def log_personal_record(
    exercise_id: str,
    exercise_name: str,
    pr_type: str,
    value: float,
    unit: str,
    date: str,
    previous_best: float | None = None,
    notes: str | None = None,
) -> str:
    """Create a Personal Record entry. Returns new page ID."""
    try:
        entry_label = f"{exercise_name} {pr_type} – {date}"
        props: dict = {
            "Entry Label": {"title": [{"text": {"content": entry_label}}]},
            "Exercise": {"relation": [{"id": exercise_id}]},
            "PR Type": {"select": {"name": pr_type}},
            "Value": {"number": value},
            "Unit": {"select": {"name": unit}},
            "Date": {"date": {"start": date}},
        }
        if previous_best is not None:
            props["Previous Best"] = {"number": previous_best}
        if notes:
            props["Notes"] = {"rich_text": [{"text": {"content": notes}}]}

        page = _notion.pages.create(
            parent={"database_id": config.NOTION_PERSONAL_RECORDS_DB_ID},
            properties=props,
        )
        return page["id"]
    except APIResponseError as e:
        logger.error("log_personal_record failed: %s", e)
        raise


def get_personal_records(exercise_id: str | None = None) -> list[dict]:
    """Return all PRs, optionally filtered by exercise."""
    try:
        kwargs: dict = {
            "database_id": config.NOTION_PERSONAL_RECORDS_DB_ID,
            "sorts": [{"property": "Date", "direction": "descending"}],
        }
        if exercise_id:
            kwargs["filter"] = {
                "property": "Exercise",
                "relation": {"contains": exercise_id},
            }
        pages = _paginate(_notion.databases.query, **kwargs)
        return [_parse_pr(p) for p in pages]
    except APIResponseError as e:
        logger.error("get_personal_records failed: %s", e)
        raise


def _parse_pr(page: dict) -> dict:
    return {
        "id": page["id"],
        "label": _title_text(page, "Entry Label"),
        "exercise_id": (_relation_ids(page, "Exercise") or [None])[0],
        "pr_type": _select(page, "PR Type"),
        "value": _number(page, "Value"),
        "unit": _select(page, "Unit"),
        "date": _date_start(page, "Date"),
        "previous_best": _number(page, "Previous Best"),
        "notes": _rich_text(page, "Notes"),
    }


# ---------------------------------------------------------------------------
# Body Metrics
# ---------------------------------------------------------------------------

def log_body_metrics(
    date: str,
    body_weight_kg: float | None = None,
    body_fat_pct: float | None = None,
    muscle_mass_kg: float | None = None,
    chest: float | None = None,
    waist: float | None = None,
    hips: float | None = None,
    arms: float | None = None,
    thighs: float | None = None,
    measurement_unit: str = "cm",
    notes: str | None = None,
) -> str:
    """Create a Body Metrics entry. Returns new page ID."""
    try:
        props: dict = {
            "Entry": {"title": [{"text": {"content": date}}]},
            "Date": {"date": {"start": date}},
            "Measurement Unit": {"select": {"name": measurement_unit}},
        }
        for prop, val in [
            ("Body Weight (kg)", body_weight_kg),
            ("Body Fat %", body_fat_pct),
            ("Muscle Mass (kg)", muscle_mass_kg),
            ("Chest", chest),
            ("Waist", waist),
            ("Hips", hips),
            ("Arms", arms),
            ("Thighs", thighs),
        ]:
            if val is not None:
                props[prop] = {"number": val}
        if notes:
            props["Notes"] = {"rich_text": [{"text": {"content": notes}}]}

        page = _notion.pages.create(
            parent={"database_id": config.NOTION_BODY_METRICS_DB_ID},
            properties=props,
        )
        return page["id"]
    except APIResponseError as e:
        logger.error("log_body_metrics failed: %s", e)
        raise


def get_recent_body_metrics(days: int = 30) -> list[dict]:
    """Return Body Metrics entries from last N days."""
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        pages = _paginate(
            _notion.databases.query,
            database_id=config.NOTION_BODY_METRICS_DB_ID,
            filter={"property": "Date", "date": {"on_or_after": since}},
            sorts=[{"property": "Date", "direction": "descending"}],
        )
        return [_parse_body_metrics(p) for p in pages]
    except APIResponseError as e:
        logger.error("get_recent_body_metrics failed: %s", e)
        raise


def _parse_body_metrics(page: dict) -> dict:
    return {
        "id": page["id"],
        "entry": _title_text(page, "Entry"),
        "date": _date_start(page, "Date"),
        "body_weight_kg": _number(page, "Body Weight (kg)"),
        "body_fat_pct": _number(page, "Body Fat %"),
        "muscle_mass_kg": _number(page, "Muscle Mass (kg)"),
        "chest": _number(page, "Chest"),
        "waist": _number(page, "Waist"),
        "hips": _number(page, "Hips"),
        "arms": _number(page, "Arms"),
        "thighs": _number(page, "Thighs"),
        "measurement_unit": _select(page, "Measurement Unit"),
        "notes": _rich_text(page, "Notes"),
    }
