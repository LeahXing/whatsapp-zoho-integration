import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "processing_state.db"


def initialize_database():
    with sqlite3.connect(DB_PATH) as conn:
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
