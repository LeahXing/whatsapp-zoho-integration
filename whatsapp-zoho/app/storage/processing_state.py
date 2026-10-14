import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "processing_state.db"

def initialize_database():
    with sqlite3.connect(DB_PATH) as conn:

        # Existing table: WhatsApp message processing
        conn.execute("""
            CREATE TABLE IF NOT EXISTS message_processing (
                message_id TEXT PRIMARY KEY,
                zoho_message_id TEXT,
                routing_completed INTEGER DEFAULT 0,
                deal_completed INTEGER DEFAULT 0,
                media_completed INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # New table: WhatsApp -> Zoho Notes synchronization
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_note_sync (
                message_id TEXT NOT NULL,
                module_name TEXT NOT NULL,
                record_id TEXT NOT NULL,
                note_id TEXT,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (message_id, module_name, record_id)
            )
        """)

def save_processing_state(
    message_id: str,
    zoho_message_id: str = None,
    routing_completed: bool = False,
    deal_completed: bool = False,
    media_completed: bool = False,
):
    """
    Save processing progress for a WhatsApp message.

    Completed stages remain completed on subsequent calls.
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO message_processing (
                message_id,
                zoho_message_id,
                routing_completed,
                deal_completed,
                media_completed
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                zoho_message_id = COALESCE(
                    excluded.zoho_message_id,
                    message_processing.zoho_message_id
                ),
                routing_completed = MAX(
                    message_processing.routing_completed,
                    excluded.routing_completed
                ),
                deal_completed = MAX(
                    message_processing.deal_completed,
                    excluded.deal_completed
                ),
                media_completed = MAX(
                    message_processing.media_completed,
                    excluded.media_completed
                ),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                message_id,
                zoho_message_id,
                int(routing_completed),
                int(deal_completed),
                int(media_completed),
            ),
        )

def get_note_sync_state(
    message_id: str,
    module_name: str,
    record_id: str,
):
    """
    Retrieve the synchronization state for one WhatsApp
    message associated with one Zoho CRM record.
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """
            SELECT
                message_id,
                module_name,
                record_id,
                note_id,
                sync_status
            FROM whatsapp_note_sync
            WHERE message_id = ?
              AND module_name = ?
              AND record_id = ?
            """,
            (message_id, module_name, record_id),
        ).fetchone()

        return dict(row) if row else None

def save_note_sync_state(
    message_id: str,
    module_name: str,
    record_id: str,
    note_id: str = None,
    sync_status: str = "pending",
):
    """
    Save the synchronization state of a WhatsApp message
    for a specific Zoho CRM record.
    """

    if sync_status not in ("pending", "completed"):
        raise ValueError("Invalid sync_status.")

    if sync_status == "completed" and not note_id:
        raise ValueError("note_id is required for completed synchronization.")

    with sqlite3.connect(DB_PATH, timeout=30) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            """
            SELECT note_id
            FROM whatsapp_note_sync
            WHERE message_id = ?
            AND module_name = ?
            AND record_id = ?
            """,
            (message_id, module_name, record_id),
        ).fetchone()

        if (
            existing
            and existing[0]
            and note_id
            and existing[0] != note_id
        ):
            raise ValueError(
                f"Conflicting Zoho Note IDs: "
                f"existing={existing[0]}, new={note_id}"
            )
        conn.execute(
            """
            INSERT INTO whatsapp_note_sync (
                message_id,
                module_name,
                record_id,
                note_id,
                sync_status
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(message_id, module_name, record_id)
            DO UPDATE SET
                note_id = COALESCE(
                    whatsapp_note_sync.note_id,
                    excluded.note_id
                ),
                sync_status = CASE
                    WHEN whatsapp_note_sync.sync_status = 'completed'
                    THEN 'completed'
                    ELSE excluded.sync_status
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                message_id,
                module_name,
                record_id,
                note_id,
                sync_status,
            ),
        )