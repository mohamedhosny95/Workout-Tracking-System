import logging
from datetime import datetime, timedelta, timezone
from notion_client import Client
from notion_client.errors import APIResponseError
import config

logger = logging.getLogger(__name__)

_notion = Client(auth=config.NOTION_API_KEY)


def _title(page: dict) -> str:
    props = page["properties"]
    for key in ("Name", "Entry Label"):
        if key in props:
            title_parts = props[key]["title"]
            return title_parts[0]["plain_text"] if title_parts else ""
    return ""


def _prop(page: dict, name: str, kind: str):
    props = page.get("properties", {})
    p = props.get(name)
    if p is None:
        return None
    if kind == "select":
        return p["select"]["name"] if p.get("select") else None
    if kind == "multi_select":
        return [o["name"] for o in p.get("multi_select", [])]
    if kind == "number":
        return p.get("number")
    if kind == "rich_text":
        parts = p.get("rich_text", [])
        return parts[0]["plain_text"] if parts else None
    if kind == "date":
        d = p.get("date")
        return d["start"] if d else None
    if kind == "relation":
        return [r["id"] for r in p.get("relation", [])]
    return None


def search_exercises(query: str) -> list[dict]:
    """Filter Exercise Library where Name contains query (case-insensitive)."""
    try:
        results = []
        cursor = None
        while True:
            kwargs = {
                "database_id": config.NOTION_EXERCISE_LIBRARY_DB_ID,
                "filter": {
                    "property": "Name",
                    "title": {"contains": query},
                },
            }
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = _notion.databases.query(**kwargs)
            for page in resp["results"]:
                results.append(_parse_exercise(page))
            if not resp.get("has_more"):
                break
            cursor = resp["next_cursor"]
        return results
    except APIResponseError as e:
        logger.error("search_exercises failed: %s", e)
        raise


def get_all_exercises() -> list[dict]:
    """Return full Exercise Library sorted by Name."""
    try:
        results = []
        cursor = None
        while True:
            kwargs = {
                "database_id": config.NOTION_EXERCISE_LIBRARY_DB_ID,
                "sorts": [{"property": "Name", "direction": "ascending"}],
            }
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = _notion.databases.query(**kwargs)
            for page in resp["results"]:
                results.append(_parse_exercise(page))
            if not resp.get("has_more"):
                break
            cursor = resp["next_cursor"]
        return results
    except APIResponseError as e:
        logger.error("get_all_exercises failed: %s", e)
        raise


def _parse_exercise(page: dict) -> dict:
    return {
        "id": page["id"],
        "name": _title(page),
        "category": _prop(page, "Category", "select"),
        "muscle_groups": _prop(page, "Muscle Group", "multi_select") or [],
        "default_sets": _prop(page, "Default Sets", "number"),
        "default_reps": _prop(page, "Default Reps", "number"),
        "default_unit": _prop(page, "Default Weight Unit", "select"),
        "description": _prop(page, "Description", "rich_text"),
    }


def add_exercise(
    name: str,
    category: str,
    muscle_groups: list[str],
    description: str,
    sets: int,
    reps: int,
    unit: str,
) -> str:
    """Create entry in Exercise Library, return new page ID."""
    try:
        props = {
            "Name": {"title": [{"text": {"content": name}}]},
        }
        if category:
            props["Category"] = {"select": {"name": category}}
        if muscle_groups:
            props["Muscle Group"] = {"multi_select": [{"name": m} for m in muscle_groups]}
        if description:
            props["Description"] = {"rich_text": [{"text": {"content": description}}]}
        if sets is not None:
            props["Default Sets"] = {"number": sets}
        if reps is not None:
            props["Default Reps"] = {"number": reps}
        if unit:
            props["Default Weight Unit"] = {"select": {"name": unit}}

        page = _notion.pages.create(
            parent={"database_id": config.NOTION_EXERCISE_LIBRARY_DB_ID},
            properties=props,
        )
        return page["id"]
    except APIResponseError as e:
        logger.error("add_exercise failed: %s", e)
        raise


def log_workout_entry(
    session_id: str,
    exercise_id: str,
    sets: int,
    reps: int,
    weight: float,
    unit: str,
    notes: str,
    date: str,
) -> str:
    """Create entry in Workout Log, return new page ID."""
    try:
        # Build the entry label: "Exercise Name – YYYY-MM-DD"
        exercise_page = _notion.pages.retrieve(exercise_id)
        exercise_name = _title(exercise_page)
        entry_label = f"{exercise_name} – {date}"

        props = {
            "Entry Label": {"title": [{"text": {"content": entry_label}}]},
            "Date": {"date": {"start": date}},
            "Exercise": {"relation": [{"id": exercise_id}]},
            "Sets": {"number": sets},
            "Reps": {"number": reps},
            "Weight": {"number": weight},
            "Weight Unit": {"select": {"name": unit}},
            "Session ID": {"rich_text": [{"text": {"content": session_id}}]},
        }
        if notes:
            props["Notes"] = {"rich_text": [{"text": {"content": notes}}]}

        page = _notion.pages.create(
            parent={"database_id": config.NOTION_WORKOUT_LOG_DB_ID},
            properties=props,
        )
        return page["id"]
    except APIResponseError as e:
        logger.error("log_workout_entry failed: %s", e)
        raise


def get_recent_logs(days: int = 7) -> list[dict]:
    """Return Workout Log entries from last N days, sorted by Date desc."""
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        results = []
        cursor = None
        while True:
            kwargs = {
                "database_id": config.NOTION_WORKOUT_LOG_DB_ID,
                "filter": {
                    "property": "Date",
                    "date": {"on_or_after": since},
                },
                "sorts": [{"property": "Date", "direction": "descending"}],
            }
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = _notion.databases.query(**kwargs)
            for page in resp["results"]:
                results.append(_parse_log_entry(page))
            if not resp.get("has_more"):
                break
            cursor = resp["next_cursor"]
        return results
    except APIResponseError as e:
        logger.error("get_recent_logs failed: %s", e)
        raise


def _parse_log_entry(page: dict) -> dict:
    exercise_ids = _prop(page, "Exercise", "relation") or []
    return {
        "id": page["id"],
        "label": _title(page),
        "date": _prop(page, "Date", "date"),
        "exercise_id": exercise_ids[0] if exercise_ids else None,
        "sets": _prop(page, "Sets", "number"),
        "reps": _prop(page, "Reps", "number"),
        "weight": _prop(page, "Weight", "number"),
        "unit": _prop(page, "Weight Unit", "select"),
        "duration": _prop(page, "Duration (min)", "number"),
        "notes": _prop(page, "Notes", "rich_text"),
        "session_id": _prop(page, "Session ID", "rich_text"),
    }


def get_all_templates() -> list[dict]:
    """Return all Workout Templates with their linked exercise IDs."""
    try:
        results = []
        cursor = None
        while True:
            kwargs = {
                "database_id": config.NOTION_WORKOUT_TEMPLATES_DB_ID,
                "sorts": [{"property": "Name", "direction": "ascending"}],
            }
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = _notion.databases.query(**kwargs)
            for page in resp["results"]:
                results.append(_parse_template(page))
            if not resp.get("has_more"):
                break
            cursor = resp["next_cursor"]
        return results
    except APIResponseError as e:
        logger.error("get_all_templates failed: %s", e)
        raise


def _parse_template(page: dict) -> dict:
    return {
        "id": page["id"],
        "name": _title(page),
        "day_tag": _prop(page, "Day Tag", "select"),
        "notes": _prop(page, "Notes", "rich_text"),
        "exercise_ids": _prop(page, "Exercises", "relation") or [],
    }


def get_exercises_by_ids(exercise_ids: list[str]) -> list[dict]:
    """Fetch multiple exercises by their Notion page IDs (used by template handler)."""
    results = []
    for eid in exercise_ids:
        try:
            page = _notion.pages.retrieve(eid)
            results.append(_parse_exercise(page))
        except APIResponseError as e:
            logger.error("get_exercises_by_ids failed for %s: %s", eid, e)
            raise
    return results
