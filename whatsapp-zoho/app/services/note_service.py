# ============================================================
# WhatsApp -> Zoho CRM Notes Synchronization
# ============================================================

from app.repositories.zoho_repository import (
    create_zoho_note,
    get_zoho_notes,
)

from app.storage.processing_state import (
    get_note_sync_state,
    save_note_sync_state,
    claim_note_sync,
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
    
    # Check whether this WhatsApp message has already
    # been synchronized to this Zoho CRM record.
    sync_state = get_note_sync_state(
        message_id=message_id,
        module_name=module_name,
        record_id=record_id,
    )

    if sync_state and sync_state["sync_status"] == "completed":
        return {
            "status": "already_synced",
            "note_id": sync_state["note_id"],
        }

    # An earlier request may have created a Zoho Note
    # before its Note ID was saved locally.
    # Do not automatically create another Note.
    if sync_state and sync_state["sync_status"] == "pending":
        return {
            "status": "reconciliation_required",
            "note_id": sync_state["note_id"],
        }
    note_title = f"{group_name} | {sender_name} | {timestamp}"
    note_content = message_text
    existing_notes = get_zoho_notes(
        module_name=module_name,
        record_id=record_id,
    )

    marker = f"WhatsApp Message ID: {message_id}"

    for note in existing_notes:
        if marker in (note.get("Note_Content") or ""):

            existing_note_id = note.get("id")

            if not existing_note_id:
                raise ValueError(
                    "Existing Zoho Note is missing its Note ID."
                )

            save_note_sync_state(
                message_id=message_id,
                module_name=module_name,
                record_id=record_id,
                note_id=existing_note_id,
                sync_status="completed",
            )

            return {
                "status": "already_synced",
                "note_id": existing_note_id,
            }

    clean_matches = [
        note for note in existing_notes
        if note.get("Note_Title") == note_title
        and note.get("Note_Content") == note_content
    ]

    if clean_matches:
        return {
            "status": "reconciliation_required",
            "note_id": (
                clean_matches[0].get("id")
                if len(clean_matches) == 1
                else None
            ),
        }

    # Clean Zoho Note format
    # Atomically claim synchronization before creating the Note.
    claimed = claim_note_sync(
        message_id=message_id,
        module_name=module_name,
        record_id=record_id,
    )

    if not claimed:
        # Another request may already be processing this message.
        # Do not create another Zoho Note.
        return {
            "status": "reconciliation_required",
            "note_id": None,
        }

    result = create_zoho_note(
        module_name=module_name,
        record_id=record_id,
        note_title=note_title,
        note_content=note_content,
    )

    # Save the Zoho Note ID after successful creation.
    note_id = result["details"]["id"]

    save_note_sync_state(
        message_id=message_id,
        module_name=module_name,
        record_id=record_id,
        note_id=note_id,
        sync_status="completed",
    )

    return {
        "status": "created",
        "note_id": note_id,
    }