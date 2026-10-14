from unittest.mock import patch

from app.schemas.message_schema import WhatsAppMessageRequest
from app.services.message_service import process_whatsapp_message


# Test message
message = WhatsAppMessageRequest(
    chatId="test-group@g.us",
    messageId="TEST-DUPLICATE-CREATION-001",
    senderIdentity={
        "whatsappId": "test-user@c.us",
        "pushName": "Test User",
    },
    groupContext={"currentName": "Stock"},
    messageContent={"textContent": "Testing duplicate creation"},
    _displayDate="2026-10-13",
    _displayTime="19:00:00",
)


# Simulate Zoho returning DUPLICATE_DATA
duplicate_error = RuntimeError(
    "DUPLICATE_DATA: {'api_name': 'Message_ID'}"
)


with (
    patch(
        "app.services.message_service.find_whatsapp_message_by_message_id",
        side_effect=[
            None,
            {"id": "EXISTING-MESSAGE-ID"},
        ],
    ) as find_message,
    patch(
        "app.services.message_service.create_whatsapp_message",
        side_effect=duplicate_error,
    ) as create_message,
    patch(
        "app.services.message_service.find_contact_by_whatsapp_id",
        return_value={"id": "EXISTING-CONTACT-ID"},
    ),
    patch(
        "app.services.message_service.find_lead_by_whatsapp_id",
    ),
    patch(
        "app.services.message_service.sync_whatsapp_note",
        return_value={
            "status": "created",
            "note_id": "TEST-NOTE-ID",
        },
    ) as sync_note,
):
    result = process_whatsapp_message(message)

    assert result["status"] == "duplicate"
    assert result["notes"]["status"] == "created"
    assert result["zoho_message_record_id"] == "EXISTING-MESSAGE-ID"

    assert find_message.call_count == 2
    create_message.assert_called_once()
    sync_note.assert_called_once()

    print("PASS: Zoho duplicate creation error handled.")
    print("PASS: Existing WhatsApp message was found.")
    print("PASS: Notes synchronization was retried.")
    print("PASS: Result:", result)