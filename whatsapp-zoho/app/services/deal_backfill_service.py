"""Historical Deal backfill. Dry-run first; writes only missing Deal Notes jobs.

A Deal must be associated with a Contact and WhatsApp group. Conversation
start/end are optional. Group-wide backfill assumes the group represents the
Contact's relevant conversation; separate conversation IDs are needed if
unrelated customers share a group.
"""
from datetime import datetime, timezone

from app.repositories.deal_backfill_repository import (
    get_deal_for_backfill,
    find_group_messages_for_backfill,
)
from app.storage.processing_state import enqueue_note
from app.services.timezone_service import format_dubai_timestamp

def _utc(value):
    """Convert Unix seconds/milliseconds or timezone-aware ISO strings to UTC."""
    if value is None or value == "":
        return None

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

        try:
            number = float(value)
        except ValueError:
            pass
        else:
            if abs(number) > 1e11:
                number /= 1000
            return datetime.fromtimestamp(number, tz=timezone.utc)

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Datetime string must include a timezone offset")
        return parsed.astimezone(timezone.utc)

    if isinstance(value, (int, float)):
        number = float(value)
        if abs(number) > 1e11:
            number /= 1000
        return datetime.fromtimestamp(number, tz=timezone.utc)

    raise ValueError(f"Invalid datetime value: {value!r}")


def preview_or_backfill(deal_id: str, dry_run: bool = True):
    deal = get_deal_for_backfill(deal_id)
    group_id = str(deal.get("WhatsApp_Group_ID") or "").strip()
    start = _utc(deal.get("WhatsApp_Conversation_Start"))
    end = _utc(deal.get("WhatsApp_Conversation_End"))

    if not group_id:
        raise ValueError("Deal requires WhatsApp_Group_ID")
    if start is not None and end is not None and end < start:
        raise ValueError("Conversation End precedes Start")
    if not deal.get("Contact_Name"):
        raise ValueError("Deal must be associated with a Contact")

    # Backfill is allowed for inactive/closed Deals. Existing message-to-Deal
    # links are preserved; Notes may be written to this Deal independently.
    candidates = []
    skipped = {"missing_timestamp": 0, "missing_message_id": 0}

    for message in find_group_messages_for_backfill(group_id):
        mid = message.get("Message_ID")
        if not mid:
            skipped["missing_message_id"] += 1
            continue

        try:
            when = _utc(message.get("Unix_Timestamp"))
        except (ValueError, TypeError, OverflowError, OSError):
            when = None
        if when is None:
            skipped["missing_timestamp"] += 1
            continue

        if start is not None and when < start:
            continue
        if end is not None and when > end:
            continue

        candidates.append((when, str(mid), message))

    candidates.sort(key=lambda item: (item[0], item[1]))
    preview = [
        {
            "message_id": mid,
            "timestamp_utc": when.isoformat(),
            "sender": message.get("Sender_Name"),
            "message": message.get("Message"),
        }
        for when, mid, message in candidates
    ]

    response = {
        "deal_id": deal_id,
        "deal_name": deal.get("Deal_Name"),
        "group_id": group_id,
        "dry_run": dry_run,
        "matched_count": len(preview),
        "skipped": skipped,
        "messages": preview,
    }
    if dry_run:
        return response

    queued = []
    for when, mid, message in candidates:
        result = enqueue_note(
            message_id=mid,
            module_name="Deals",
            record_id=deal_id,
            group_id=group_id,
            sender_name=message.get("Sender_Name") or "Unknown",
            group_name=message.get("Group_Name") or "Unknown Group",
            message_text=message.get("Message") or "",
            unix_timestamp=when.timestamp(),
            display_timestamp=format_dubai_timestamp(when.timestamp()),
        )
        queued.append({"message_id": mid, **result})

    response["jobs"] = queued
    return response
