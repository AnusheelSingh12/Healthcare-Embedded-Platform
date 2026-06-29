from datetime import datetime

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import ClinicalItem
from app.models.movement import MovementEvent


DEFAULT_MISSING_STATUS = "Missing"
EXCLUDED_TOOLS_IN_UIDS = {"RFID-2003", "RFID-2006", "RFID-2001", "3CA54A06"}
EXCLUDED_DASHBOARD_UIDS = {"RFID-2001", "RFID-2003", "RFID-2004", "RFID-2006", "3CA54A06"}


def infer_category(item_name: str, action: str) -> str:
    normalized_name = item_name.lower()
    if action == "CONSUMED" or "gauze" in normalized_name:
        return "Consumables"
    if "forceps" in normalized_name:
        return "Forceps"
    if "scalpel" in normalized_name:
        return "Scalpels"
    if "tray" in normalized_name:
        return "Trays"
    return "Instruments"


def infer_status(action: str) -> str:
    if action == "TOOL_OUT":
        return "Missing"
    if action == "TOOL_IN":
        return "Sterilized"
    if action == "CONSUMED":
        return "In Use"
    return "In Use"


def get_item_by_uid(db: Session, uid: str) -> ClinicalItem | None:
    return db.get(ClinicalItem, uid)


def register_serial_event(db: Session, serial_payload: dict) -> dict:
    uid = str(serial_payload["UID"]).strip()
    item_name = str(serial_payload["item_name"]).strip()
    action = str(serial_payload["action"]).strip().upper()
    gauze_count = int(serial_payload.get("gauze_count", 0))
    tools_missing = int(serial_payload.get("tools_missing", 0))
    # Use host device time at ingestion; no RTC dependency.
    event_time = datetime.now().astimezone()

    movement = MovementEvent(
        uid=uid,
        item_name=item_name,
        direction=action,
        gauze_count=gauze_count,
        tools_missing=tools_missing,
        event_time=event_time,
    )
    db.add(movement)

    item: ClinicalItem | None = None
    if uid != "BTN_RESET":
        item = get_item_by_uid(db, uid)
        if item is None:
            item = ClinicalItem(
                uid=uid,
                name=item_name,
                category=infer_category(item_name, action),
                status=infer_status(action),
            )
        else:
            item.name = item_name
            item.category = infer_category(item_name, action)
            item.status = infer_status(action)

        item.last_seen = event_time
        db.add(item)

    db.commit()

    return {
        "event": "scan",
        "uid": uid,
        "name": item_name,
        "action": action,
        "timestamp": event_time.isoformat(),
        "gauze_count": gauze_count,
        "tools_missing": tools_missing,
        "status": item.status if item else "System",
        "category": item.category if item else "System",
        "quick_stats": get_quick_stats(db, gauze_count, tools_missing),
    }


def clear_event_log(db: Session) -> None:
    db.query(MovementEvent).delete(synchronize_session=False)
    db.commit()


def _is_gauze_name(name: str) -> bool:
    return "gauze" in name.lower()


def get_tool_presence(db: Session) -> dict[str, list[dict[str, str]]]:
    latest_event = db.query(MovementEvent).order_by(MovementEvent.event_time.desc(), MovementEvent.id.desc()).first()
    if latest_event and latest_event.uid == "BTN_RESET" and latest_event.direction == "RESET_STATE":
        all_tools = db.query(ClinicalItem).order_by(ClinicalItem.name.asc()).all()
        in_tools = [
            {"uid": tool.uid, "name": tool.name, "time": latest_event.event_time.isoformat()}
            for tool in all_tools
            if not _is_gauze_name(tool.name)
            and tool.category.lower() != "consumables"
            and tool.uid not in EXCLUDED_TOOLS_IN_UIDS
        ]
        return {"in_tools": in_tools, "out_tools": []}

    reset_event = (
        db.query(MovementEvent)
        .filter(MovementEvent.direction == "RESET_STATE")
        .order_by(MovementEvent.event_time.desc(), MovementEvent.id.desc())
        .first()
    )

    recent_query = db.query(MovementEvent).order_by(MovementEvent.event_time.asc(), MovementEvent.id.asc())
    if reset_event is not None:
        recent_query = recent_query.filter(
            (MovementEvent.event_time > reset_event.event_time)
            | ((MovementEvent.event_time == reset_event.event_time) & (MovementEvent.id > reset_event.id))
        )
    events = recent_query.all()

    last_action_by_uid: dict[str, tuple[str, str, str]] = {}
    for event in events:
        if event.uid == "BTN_RESET":
            continue
        if _is_gauze_name(event.item_name):
            continue
        if event.direction not in {"TOOL_IN", "TOOL_OUT"}:
            continue
        last_action_by_uid[event.uid] = (event.item_name, event.direction, event.event_time.isoformat())

    known_tools = db.query(ClinicalItem).order_by(ClinicalItem.name.asc()).all()
    in_tools: list[dict[str, str]] = []
    out_tools: list[dict[str, str]] = []
    seen: set[str] = set()

    for tool in known_tools:
        if _is_gauze_name(tool.name) or tool.category.lower() == "consumables":
            continue
        seen.add(tool.uid)
        name, action, time = last_action_by_uid.get(tool.uid, (tool.name, "TOOL_IN", ""))
        row = {"uid": tool.uid, "name": name, "time": time}
        if action == "TOOL_OUT":
            out_tools.append(row)
        else:
            if tool.uid in EXCLUDED_TOOLS_IN_UIDS:
                continue
            in_tools.append(row)

    for uid, (name, action, time) in last_action_by_uid.items():
        if uid in seen:
            continue
        row = {"uid": uid, "name": name, "time": time}
        if action == "TOOL_OUT":
            out_tools.append(row)
        else:
            if uid in EXCLUDED_TOOLS_IN_UIDS:
                continue
            in_tools.append(row)

    in_tools.sort(key=lambda row: (row["name"].lower(), row["uid"]))
    out_tools.sort(key=lambda row: (row["name"].lower(), row["uid"]))
    return {"in_tools": in_tools, "out_tools": out_tools}


def get_quick_stats(db: Session, gauze_count: int | None = None, tools_missing: int | None = None) -> dict:
    total_registered = (
        db.query(func.count(ClinicalItem.uid))
        .filter(~ClinicalItem.uid.in_(EXCLUDED_DASHBOARD_UIDS))
        .scalar()
        or 0
    )

    if gauze_count is None or tools_missing is None:
        latest = db.query(MovementEvent).order_by(MovementEvent.event_time.desc(), MovementEvent.id.desc()).first()
        gauze_count = latest.gauze_count if latest else 0
        tools_missing = latest.tools_missing if latest else 0

    return {
        "total_registered": total_registered,
        "gauze_used": max(int(gauze_count or 0), 0),
        "tools_missing": max(int(tools_missing or 0), 0),
    }


def get_category_breakdown(db: Session) -> list[dict[str, int | str]]:
    missing_case = case((ClinicalItem.status == DEFAULT_MISSING_STATUS, 1), else_=0)
    rows = (
        db.query(
            ClinicalItem.category,
            func.count(ClinicalItem.uid),
            func.sum(missing_case),
        )
        .group_by(ClinicalItem.category)
        .order_by(ClinicalItem.category.asc())
        .all()
    )
    return [
        {
            "category": category,
            "count": int(total or 0),
            "out_count": int(missing or 0),
            "in_count": max(int(total or 0) - int(missing or 0), 0),
        }
        for category, total, missing in rows
    ]


def get_all_items(db: Session) -> list[dict[str, str | None]]:
    rows = db.query(ClinicalItem).order_by(ClinicalItem.uid.asc()).all()
    return [
        {
            "uid": item.uid,
            "name": item.name,
            "category": item.category,
            "status": item.status,
            "last_seen": item.last_seen.isoformat() if item.last_seen else None,
        }
        for item in rows
    ]


def get_recent_events(db: Session, limit: int = 300) -> list[dict[str, str | int]]:
    events = (
        db.query(MovementEvent)
        .order_by(MovementEvent.event_time.desc(), MovementEvent.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "uid": event.uid,
            "name": event.item_name,
            "action": event.direction,
            "timestamp": event.event_time.isoformat(),
            "gauze_count": event.gauze_count,
            "tools_missing": event.tools_missing,
        }
        for event in events
    ]


def update_item(
    db: Session,
    uid: str,
    *,
    new_uid: str | None,
    name: str | None,
    category: str | None,
    status: str | None,
) -> dict | None:
    item = get_item_by_uid(db, uid)
    if item is None:
        return None

    target_uid = item.uid
    if new_uid and new_uid != item.uid:
        duplicate = get_item_by_uid(db, new_uid)
        if duplicate is not None:
            raise ValueError("Target UID already exists")

        old_uid = item.uid
        item.uid = new_uid
        target_uid = new_uid

        # Keep movement history linked after UID rename.
        db.query(MovementEvent).filter(MovementEvent.uid == old_uid).update(
            {MovementEvent.uid: new_uid}, synchronize_session=False
        )

    if name is not None:
        item.name = name
    if category is not None:
        item.category = category
    if status is not None:
        item.status = status

    db.add(item)
    db.commit()

    updated = get_item_by_uid(db, target_uid)
    if updated is None:
        return None

    return {
        "uid": updated.uid,
        "name": updated.name,
        "category": updated.category,
        "status": updated.status,
        "last_seen": updated.last_seen.isoformat() if updated.last_seen else None,
    }


def get_movement_sessions(db: Session, limit: int = 200) -> list[dict[str, str | None]]:
    # Legacy API compatibility: keep endpoint shape but map from event log.
    events = get_recent_events(db, limit)
    return [
        {
            "uid": event["uid"],
            "name": event["name"],
            "incoming_time": event["timestamp"] if event["action"] == "TOOL_IN" else None,
            "outgoing_time": event["timestamp"] if event["action"] == "TOOL_OUT" else None,
        }
        for event in events
    ]


def seed_items(db: Session) -> None:
    has_rows = db.query(func.count(ClinicalItem.uid)).scalar() or 0
    if has_rows:
        return

    seed_data = [
        ClinicalItem(uid="4D055B06", name="Gauze Pack", category="Consumables", status="Sterilized"),
        ClinicalItem(uid="426F3406", name="Kidney Tray", category="Trays", status="Sterilized"),
        ClinicalItem(uid="D3CCF605", name="Straight Artery Forceps", category="Forceps", status="Sterilized"),
        ClinicalItem(uid="EEF73206", name="Curved Artery Forceps", category="Forceps", status="Sterilized"),
        ClinicalItem(uid="ACA54A06", name="Scalpel", category="Scalpels", status="Sterilized"),
        ClinicalItem(uid="D1663806", name="Forceps", category="Forceps", status="Sterilized"),
    ]
    db.add_all(seed_data)
    db.commit()
