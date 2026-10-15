from unittest.mock import patch, MagicMock
from app.services.message_service import process_whatsapp_message


def test_deal_notes():
    message = MagicMock()
    message.messageId = "TEST-DEAL-NOTES-001"
    message.chatId = "TEST-GROUP"
    message.senderIdentity.whatsappId = "TEST-SENDER"
    message.senderIdentity.pushName = "Test Sender"
    message.groupContext.currentName = "Stock Group"
    message.displayDate = "2026-10-13"
    message.displayTime = "19:00:00"
    message.messageContent.textContent = "Buy 100 shares"

    with (
        patch(
            "app.services.message_service.find_whatsapp_message_by_message_id",
            return_value=None,
        ),
        patch(
            "app.services.message_service.create_whatsapp_message",
            return_value={"details": {"id": "TEST-MESSAGE-RECORD"}},
        ),
        patch(
            "app.services.message_service.analyze_commercial_message",
            return_value={"qualified": True},
        ),
        patch(
            "app.services.message_service.route_whatsapp_sender",
            return_value={
                "person_type": "contact",
                "person_id": "TEST-CONTACT-ID",
                "action": "EXISTING_CONTACT",
            },
        ),
        patch(
            "app.services.message_service.process_deal",
            return_value={
                "deal_id": "TEST-DEAL-ID",
                "deal_action": "EXISTING_DEAL",
            },
        ),
        patch(
            "app.services.message_service.upload_media_to_zoho",
            return_value={"status": "skipped"},
        ),
        patch(
            "app.services.message_service.sync_whatsapp_note",
            return_value={"status": "created", "note_id": "TEST-NOTE"},
        ) as mock_sync,
    ):
        result = process_whatsapp_message(message)

    assert mock_sync.call_count == 1
    assert mock_sync.call_args.kwargs["module_name"] == "Contacts"
    assert mock_sync.call_args.kwargs["record_id"] == "TEST-CONTACT-ID"
    assert result["deal_notes"]["status"] == "disabled"

    print("PASS: Contact Note synchronized.")
    print("PASS: No duplicate Deal Note created.")
    print("PASS: No real Zoho API calls were made.")


if __name__ == "__main__":
    test_deal_notes()