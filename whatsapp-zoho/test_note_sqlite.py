import tempfile
from pathlib import Path
from unittest.mock import patch

from app.storage import processing_state


def test_sqlite_note_sync():

    with tempfile.TemporaryDirectory() as temp_dir:

        test_db = Path(temp_dir) / "test_processing_state.db"

        with patch.object(processing_state, "DB_PATH", test_db):

            # Create tables in the temporary database
            processing_state.initialize_database()

            # First attempt should claim the message
            first_claim = processing_state.claim_note_sync(
                message_id="TEST-SQLITE-001",
                module_name="Contacts",
                record_id="TEST-CONTACT-001",
            )

            assert first_claim is True

            # Second attempt must not claim the same message
            second_claim = processing_state.claim_note_sync(
                message_id="TEST-SQLITE-001",
                module_name="Contacts",
                record_id="TEST-CONTACT-001",
            )

            assert second_claim is False

            # Verify pending status
            pending_state = processing_state.get_note_sync_state(
                message_id="TEST-SQLITE-001",
                module_name="Contacts",
                record_id="TEST-CONTACT-001",
            )

            assert pending_state["sync_status"] == "pending"
            assert pending_state["note_id"] is None

            # Mark synchronization as completed
            processing_state.save_note_sync_state(
                message_id="TEST-SQLITE-001",
                module_name="Contacts",
                record_id="TEST-CONTACT-001",
                note_id="TEST-ZOHO-NOTE-001",
                sync_status="completed",
            )

            # Verify completed status
            completed_state = processing_state.get_note_sync_state(
                message_id="TEST-SQLITE-001",
                module_name="Contacts",
                record_id="TEST-CONTACT-001",
            )

            assert completed_state["sync_status"] == "completed"
            assert completed_state["note_id"] == "TEST-ZOHO-NOTE-001"

    print("PASS: First SQLite claim succeeds.")
    print("PASS: Duplicate SQLite claim is rejected.")
    print("PASS: Pending synchronization is recorded.")
    print("PASS: Completed synchronization is recorded.")
    print("PASS: Production SQLite database was not modified.")


if __name__ == "__main__":
    test_sqlite_note_sync()