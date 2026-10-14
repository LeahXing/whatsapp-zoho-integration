# ============================================================
# WhatsApp -> Zoho CRM Notes Synchronization
# ============================================================

from app.repositories.zoho_repository import (
    create_zoho_note,
    get_zoho_notes,
)


def sync_whatsapp_note(
    module_name: str,
    record_id: str,
    message_id: str,
    sender_name: str,
    group_name: str,
    timestamp: str,
    message_text: str,
) -> dict:
    """
    Create a Zoho Note for one WhatsApp message.

    Prevent duplicates by checking the Message_ID
    in existing Notes for the destination CRM record.
    """

    if not message_id:
        raise ValueError("message_id is required.")

    if not record_id:
        raise ValueError("record_id is required.")

    existing_notes = get_zoho_notes(
        module_name=module_name,
        record_id=record_id,
    )

    marker = f"WhatsApp Message ID: {message_id}"

    for note in existing_notes:
        if marker in (note.get("Note_Content") or ""):
            return {
                "status": "already_synced",
                "note_id": note.get("id"),
            }

    note_title = f"WhatsApp | {group_name} | {timestamp}"

    note_content = (
        f"Sender: {sender_name}\n"
        f"Group: {group_name}\n"
        f"Timestamp: {timestamp}\n\n"
        f"Message:\n{message_text}\n\n"
        f"{marker}"
    )

    result = create_zoho_note(
        module_name=module_name,
        record_id=record_id,
        note_title=note_title,
        note_content=note_content,
    )

    return {
        "status": "created",
        "note_id": result["details"]["id"],
    }