"""Persistent WhatsApp group conversation boundaries and CRM membership.

Additive SQLite state; does not modify existing Notes queue or Deal routing.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / 'processing_state.db'


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=30000')
    return conn


def initialize_group_conversation_tables():
    with _connect() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS whatsapp_group_conversations (
            group_id TEXT PRIMARY KEY,
            conversation_start_utc REAL NOT NULL,
            first_lead_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS whatsapp_group_crm_members (
            group_id TEXT NOT NULL,
            module_name TEXT NOT NULL CHECK(module_name IN ('Leads','Contacts')),
            record_id TEXT NOT NULL,
            whatsapp_id TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(group_id,module_name,record_id)
        )''')
        conn.execute('''CREATE INDEX IF NOT EXISTS idx_group_crm_members_active
            ON whatsapp_group_crm_members(group_id,active)''')


def establish_group_start(group_id: str, first_message_timestamp: float, first_lead_id: str):
    """First writer wins. Never shift a group's start when later Leads appear."""
    if not group_id or not first_lead_id:
        raise ValueError('group_id and first_lead_id are required')
    timestamp = float(first_message_timestamp)
    datetime.fromtimestamp(timestamp, tz=timezone.utc)  # validate timestamp
    with _connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''INSERT OR IGNORE INTO whatsapp_group_conversations
            (group_id,conversation_start_utc,first_lead_id) VALUES(?,?,?)''',
            (group_id,timestamp,str(first_lead_id)))
        row = conn.execute('''SELECT * FROM whatsapp_group_conversations
            WHERE group_id=?''', (group_id,)).fetchone()
        return dict(row)


def get_group_start(group_id: str):
    with _connect() as conn:
        row = conn.execute('''SELECT conversation_start_utc FROM whatsapp_group_conversations
            WHERE group_id=?''', (group_id,)).fetchone()
        return row['conversation_start_utc'] if row else None


def register_group_member(group_id: str, module_name: str, record_id: str,
                          whatsapp_id: str):
    if module_name not in ('Leads', 'Contacts'):
        raise ValueError('module_name must be Leads or Contacts')
    if not all((group_id, record_id, whatsapp_id)):
        raise ValueError('group_id, record_id, whatsapp_id are required')
    with _connect() as conn:
        conn.execute('''INSERT INTO whatsapp_group_crm_members
            (group_id,module_name,record_id,whatsapp_id,active)
            VALUES(?,?,?,?,1)
            ON CONFLICT(group_id,module_name,record_id) DO UPDATE SET
                whatsapp_id=excluded.whatsapp_id,active=1,updated_at=CURRENT_TIMESTAMP''',
            (group_id,module_name,str(record_id),whatsapp_id))


def list_active_group_members(group_id: str):
    with _connect() as conn:
        rows = conn.execute('''SELECT module_name,record_id,whatsapp_id
            FROM whatsapp_group_crm_members WHERE group_id=? AND active=1
            ORDER BY module_name,record_id''', (group_id,)).fetchall()
        return [dict(row) for row in rows]


def deactivate_group_member(group_id: str, module_name: str, record_id: str):
    """Useful when a Lead converts to a Contact; preserve historical association."""
    with _connect() as conn:
        conn.execute('''UPDATE whatsapp_group_crm_members
            SET active=0,updated_at=CURRENT_TIMESTAMP
            WHERE group_id=? AND module_name=? AND record_id=?''',
            (group_id,module_name,str(record_id)))
