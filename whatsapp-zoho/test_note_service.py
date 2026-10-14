from unittest.mock import patch

from app.services.note_service import sync_whatsapp_note


def test_clean_note_format():

    with (
        patch(
            "app.services.note_service.get_note_sync_state",
            return_value=None,
        ),
        patch(
            "app.services.note_service.get_zoho_notes",
            return_value=[],
        ),
        patch(
            "app.services.note_service.claim_note_sync",
            return_value=True,
        ),
        patch(
            "app.services.note_service.create_zoho_note",
            return_value={"details": {"id": "TEST-NOTE-ID"}},
        ) as mock_create,
        patch(
            "app.services.note_service.save_note_sync_state",
        ) as mock_save,
    ):

        result = sync_whatsapp_note(
            module_name="Contacts",
            record_id="TEST-CONTACT-ID",
            message_id="TEST-MESSAGE-001",
            sender_name="Juan",
            group_name="Stock",
            timestamp="2026-10-13 19:00:00",
            message_text="can you reduce the gold price",
        )

        mock_create.assert_called_once_with(
            module_name="Contacts",
            record_id="TEST-CONTACT-ID",
            note_title="Stock | Juan | 2026-10-13 19:00:00",
            note_content="can you reduce the gold price",
        )

        mock_save.assert_called_once_with(
            message_id="TEST-MESSAGE-001",
            module_name="Contacts",
            record_id="TEST-CONTACT-ID",
            note_id="TEST-NOTE-ID",
            sync_status="completed",
        )

        assert result == {
            "status": "created",
            "note_id": "TEST-NOTE-ID",
        }

    print("PASS: Clean Note Title and Content.")
    print("PASS: Completed synchronization recorded.")
    print("PASS: No real Zoho API or SQLite calls.")

def test_duplicate_note_prevention():

    with (
        patch(
            "app.services.note_service.get_note_sync_state",
            return_value={
                "message_id": "TEST-MESSAGE-001",
                "module_name": "Contacts",
                "record_id": "TEST-CONTACT-ID",
                "note_id": "EXISTING-NOTE-ID",
                "sync_status": "completed",
            },
        ),
        patch(
            "app.services.note_service.create_zoho_note",
        ) as mock_create,
        patch(
            "app.services.note_service.claim_note_sync",
        ) as mock_claim,
    ):

        result = sync_whatsapp_note(
            module_name="Contacts",
            record_id="TEST-CONTACT-ID",
            message_id="TEST-MESSAGE-001",
            sender_name="Juan",
            group_name="Stock",
            timestamp="2026-10-13 19:00:00",
            message_text="can you reduce the gold price",
        )

        assert result == {
            "status": "already_synced",
            "note_id": "EXISTING-NOTE-ID",
        }

        mock_create.assert_not_called()
        mock_claim.assert_not_called()

    print("PASS: Duplicate Note creation prevented.")

def test_pending_note_prevention():

    with (
        patch(
            "app.services.note_service.get_note_sync_state",
            return_value={
                "message_id": "TEST-PENDING-001",
                "module_name": "Contacts",
                "record_id": "TEST-CONTACT-ID",
                "note_id": None,
                "sync_status": "pending",
            },
        ),
        patch(
            "app.services.note_service.create_zoho_note",
        ) as mock_create,
        patch(
            "app.services.note_service.claim_note_sync",
        ) as mock_claim,
    ):

        result = sync_whatsapp_note(
            module_name="Contacts",
            record_id="TEST-CONTACT-ID",
            message_id="TEST-PENDING-001",
            sender_name="Juan",
            group_name="Stock",
            timestamp="2026-10-13 19:00:00",
            message_text="can you reduce the gold price",
        )

        assert result == {
            "status": "reconciliation_required",
            "note_id": None,
        }

        mock_create.assert_not_called()
        mock_claim.assert_not_called()

    print("PASS: Pending synchronization blocks duplicate creation.")

def test_existing_legacy_note():

    with (
        patch(
            "app.services.note_service.get_note_sync_state",
            return_value=None,
        ),
        patch(
            "app.services.note_service.get_zoho_notes",
            return_value=[
                {
                    "id": "LEGACY-NOTE-ID",
                    "Note_Content": (
                        "WhatsApp Message ID: TEST-LEGACY-001\n"
                        "Message: Existing WhatsApp message"
                    ),
                }
            ],
        ),
        patch(
            "app.services.note_service.create_zoho_note",
        ) as mock_create,
        patch(
            "app.services.note_service.save_note_sync_state",
        ) as mock_save,
    ):

        result = sync_whatsapp_note(
            module_name="Contacts",
            record_id="TEST-CONTACT-ID",
            message_id="TEST-LEGACY-001",
            sender_name="Juan",
            group_name="Stock",
            timestamp="2026-10-13 19:00:00",
            message_text="Existing WhatsApp message",
        )

        assert result == {
            "status": "already_synced",
            "note_id": "LEGACY-NOTE-ID",
        }

        mock_create.assert_not_called()

        mock_save.assert_called_once_with(
            message_id="TEST-LEGACY-001",
            module_name="Contacts",
            record_id="TEST-CONTACT-ID",
            note_id="LEGACY-NOTE-ID",
            sync_status="completed",
        )

    print("PASS: Existing legacy Note recognized without duplication.")

if __name__ == "__main__":
    test_clean_note_format()
    test_duplicate_note_prevention()
    test_pending_note_prevention()
    test_existing_legacy_note()