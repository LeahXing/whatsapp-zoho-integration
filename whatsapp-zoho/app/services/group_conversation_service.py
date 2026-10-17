"""Group-wide Lead/Contact WhatsApp Notes synchronization.

Requires app.storage.group_conversation_state and existing Zoho group-message
repository. Deals remain managed by the existing Deal services.
"""
from datetime import datetime, timezone

from app.repositories.deal_backfill_repository import find_group_messages_for_backfill
from app.storage.group_conversation_state import (
    establish_group_start,
    get_group_start,
    register_group_member as save_group_member,
    list_active_group_members,
    deactivate_group_member,
)
from app.storage.processing_state import enqueue_note
from app.services.timezone_service import format_dubai_timestamp

def normalize_timestamp(value):
    """Return Unix seconds from seconds, milliseconds, or ISO-8601 with offset."""
    if value is None or value == "":
        raise ValueError("Original WhatsApp timestamp is required")
    if isinstance(value, str):
        value = value.strip()
        try:
            value = float(value)
        except ValueError:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("Timestamp must include a timezone offset")
            return parsed.timestamp()
    seconds = float(value)
    if seconds > 1e11:
        seconds /= 1000
    datetime.fromtimestamp(seconds, tz=timezone.utc)
    return seconds


def _enqueue(message_id, group_id, sender_name, group_name, message_text,
             timestamp, module_name, record_id):
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return enqueue_note(
        message_id=str(message_id), module_name=module_name,
        record_id=str(record_id), group_id=group_id,
        sender_name=sender_name or "Unknown",
        group_name=group_name or "Unknown Group",
        message_text=message_text or "", unix_timestamp=timestamp,
        display_timestamp=format_dubai_timestamp(dt.timestamp()),
    )


def register_person_and_backfill(*, group_id, whatsapp_id, module_name,
                                 record_id, first_lead_created=False,
                                 triggering_timestamp=None):
    """Register a CRM person and enqueue the group's shared history.

    Caller must set first_lead_created only after successful Zoho Lead creation.
    The first successful group-start insertion wins, including on retries.
    """
    if module_name not in ("Leads", "Contacts"):
        raise ValueError("Only Leads and Contacts are supported")
    if first_lead_created:
        if module_name != "Leads":
            raise ValueError("Only a new Lead can establish group start")
        establish_group_start(group_id, normalize_timestamp(triggering_timestamp), record_id)

    save_group_member(group_id, module_name, record_id, whatsapp_id)
    start = get_group_start(group_id)
    if start is None:
        return {"status": "registered_waiting_for_first_lead", "queued": 0}

    messages = []
    for item in find_group_messages_for_backfill(group_id):
        if not item.get("Message_ID"):
            continue
        try:
            ts = normalize_timestamp(item.get("Unix_Timestamp"))
        except (ValueError, TypeError, OverflowError, OSError):
            continue
        if ts >= start:
            messages.append((ts, str(item["Message_ID"]), item))
    messages.sort(key=lambda row: (row[0], row[1]))
    for ts, mid, item in messages:
        _enqueue(mid, group_id, item.get("Sender_Name"), item.get("Group_Name"),
                 item.get("Message"), ts, module_name, record_id)
    return {"status": "backfill_queued", "conversation_start_utc": start,
            "queued": len(messages)}


def queue_group_message_notes(message):
    """Fan out an incoming group message to every registered active CRM person."""
    group_id = message.chatId
    start = get_group_start(group_id)
    if start is None:
        return {"status": "waiting_for_first_lead", "queued": 0}
    raw = message.messageMeta.unixTimestamp if message.messageMeta else None
    try:
        ts = normalize_timestamp(raw)
    except (ValueError, TypeError, OverflowError, OSError):
        return {"status": "missing_or_invalid_timestamp", "queued": 0}
    if ts < start:
        return {"status": "before_group_start", "queued": 0}
    members = list_active_group_members(group_id)
    for member in members:
        _enqueue(message.messageId, group_id, message.senderIdentity.pushName,
                 message.groupContext.currentName if message.groupContext else None,
                 message.messageContent.textContent if message.messageContent else None,
                 ts, member["module_name"], member["record_id"])
    return {"status": "queued", "queued": len(members)}


def transfer_lead_to_contact(*, group_id, lead_id, contact_id, whatsapp_id):
    """Move future sync to Contact; queue shared history on Contact separately."""
    result = register_person_and_backfill(
        group_id=group_id, whatsapp_id=whatsapp_id,
        module_name="Contacts", record_id=contact_id)
    deactivate_group_member(group_id, "Leads", lead_id)
    return result
