from unittest.mock import patch

from app.schemas.message_schema import WhatsAppMessageRequest
from app.services.message_service import process_whatsapp_message


message = WhatsAppMessageRequest(
    chatId="test-group@g.us",
    messageId="TEST-RETRY-001",
    senderIdentity={
        "whatsappId": "test-user@c.us",
        "pushName": "Test User",
    },
    groupContext={"currentName": "Stock"},
    messageContent={"textContent": "Testing Notes retry"},
    _displayDate="2026-10-13",
    _displayTime="19:00:00",
)


with (
    patch(
        "app.services.message_service.find_whatsapp_message_by_message_id",
        return_value={
            "id": "EXISTING-MESSAGE-ID",
            "Deal": {
                "id": "EXISTING-DEAL-ID"
            },
        },
    ),
    patch(
        "app.services.message_service.find_contact_by_whatsapp_id",
        return_value={"id": "EXISTING-CONTACT-ID"},
),
    patch(
        "app.services.message_service.find_lead_by_whatsapp_id",
    ),
    patch(
        "app.services.message_service.create_whatsapp_message"
    ) as create_message,
    patch(
        "app.services.message_service.sync_whatsapp_note",
        return_value={"status": "created", "note_id": "TEST-NOTE-ID"},
    ) as sync_note,
):
    result = process_whatsapp_message(message)

    assert result["status"] == "duplicate"
    print("DEBUG result:", result)
    assert result["notes"]["status"] == "created"
    create_message.assert_not_called()

    assert result["deal_notes"]["status"] == "disabled"

    assert sync_note.call_count == 1

    assert sync_note.call_args.kwargs["module_name"] == "Contacts"
    assert sync_note.call_args.kwargs["record_id"] == "EXISTING-CONTACT-ID"

    print("PASS: Existing message was not recreated.")
    print("PASS: Notes synchronization was retried.")
    print("PASS: Notes retry result:", result["notes"])