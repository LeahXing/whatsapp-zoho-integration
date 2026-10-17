"""Durable local processing and WhatsApp Notes queue (SQLite)."""
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / 'processing_state.db'


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=30000')
    return conn


def initialize_database():
    with _connect() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS message_processing (
            message_id TEXT PRIMARY KEY, zoho_message_id TEXT,
            routing_completed INTEGER DEFAULT 0, deal_completed INTEGER DEFAULT 0,
            media_completed INTEGER DEFAULT 0, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS whatsapp_note_sync (
            message_id TEXT NOT NULL, module_name TEXT NOT NULL, record_id TEXT NOT NULL,
            note_id TEXT, sync_status TEXT NOT NULL DEFAULT 'pending',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(message_id, module_name, record_id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS whatsapp_note_queue (
            message_id TEXT NOT NULL, module_name TEXT NOT NULL, record_id TEXT NOT NULL,
            group_id TEXT NOT NULL, sender_name TEXT, group_name TEXT, message_text TEXT,
            unix_timestamp REAL NOT NULL, display_timestamp TEXT NOT NULL,
            scheduled_at TEXT NOT NULL, queue_status TEXT NOT NULL DEFAULT 'queued',
            attempt_count INTEGER NOT NULL DEFAULT 0, note_id TEXT, last_error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(message_id, module_name, record_id))''')
        conn.execute('''CREATE INDEX IF NOT EXISTS idx_note_queue_due
            ON whatsapp_note_queue(queue_status, scheduled_at, unix_timestamp, message_id)''')


def save_processing_state(message_id: str, zoho_message_id: str = None,
                          routing_completed: bool = False, deal_completed: bool = False,
                          media_completed: bool = False):
    with _connect() as conn:
        conn.execute('''INSERT INTO message_processing
            (message_id,zoho_message_id,routing_completed,deal_completed,media_completed)
            VALUES(?,?,?,?,?) ON CONFLICT(message_id) DO UPDATE SET
            zoho_message_id=COALESCE(excluded.zoho_message_id,message_processing.zoho_message_id),
            routing_completed=MAX(message_processing.routing_completed,excluded.routing_completed),
            deal_completed=MAX(message_processing.deal_completed,excluded.deal_completed),
            media_completed=MAX(message_processing.media_completed,excluded.media_completed),
            updated_at=CURRENT_TIMESTAMP''', (message_id, zoho_message_id,
                int(routing_completed), int(deal_completed), int(media_completed)))


def get_note_sync_state(message_id: str, module_name: str, record_id: str):
    with _connect() as conn:
        row = conn.execute('''SELECT message_id,module_name,record_id,note_id,sync_status
            FROM whatsapp_note_sync WHERE message_id=? AND module_name=? AND record_id=?''',
            (message_id,module_name,record_id)).fetchone()
        return dict(row) if row else None


def save_note_sync_state(message_id: str, module_name: str, record_id: str,
                         note_id: str = None, sync_status: str = 'pending'):
    if sync_status not in ('pending','completed'):
        raise ValueError('Invalid sync_status.')
    if sync_status == 'completed' and not note_id:
        raise ValueError('note_id is required for completed synchronization.')
    with _connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        existing = conn.execute('''SELECT note_id FROM whatsapp_note_sync
            WHERE message_id=? AND module_name=? AND record_id=?''',
            (message_id,module_name,record_id)).fetchone()
        if existing and existing[0] and note_id and existing[0] != note_id:
            raise ValueError(f'Conflicting Zoho Note IDs: existing={existing[0]}, new={note_id}')
        conn.execute('''INSERT INTO whatsapp_note_sync
            (message_id,module_name,record_id,note_id,sync_status) VALUES(?,?,?,?,?)
            ON CONFLICT(message_id,module_name,record_id) DO UPDATE SET
            note_id=COALESCE(whatsapp_note_sync.note_id,excluded.note_id),
            sync_status=CASE WHEN whatsapp_note_sync.sync_status='completed'
                THEN 'completed' ELSE excluded.sync_status END,
            updated_at=CURRENT_TIMESTAMP''',
            (message_id,module_name,record_id,note_id,sync_status))


def claim_note_sync(message_id: str, module_name: str, record_id: str) -> bool:
    with _connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        cursor = conn.execute('''INSERT OR IGNORE INTO whatsapp_note_sync
            (message_id,module_name,record_id,sync_status) VALUES(?,?,?,'pending')''',
            (message_id,module_name,record_id))
        return cursor.rowcount == 1


def enqueue_note(*, message_id, module_name, record_id, group_id,
                 sender_name, group_name, message_text, unix_timestamp,
                 display_timestamp):
    """Insert once. Never reset completed or uncertain jobs on duplicates."""
    if module_name not in ('Leads','Contacts','Deals') or not record_id or not message_id:
        raise ValueError('Invalid Notes destination or message ID')
    seconds = int(os.getenv('WHATSAPP_SYNC_BUFFER_SECONDS', '10'))
    if seconds < 0:
        raise ValueError('WHATSAPP_SYNC_BUFFER_SECONDS must be >= 0')
    scheduled_at = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
    with _connect() as conn:
        cursor = conn.execute('''INSERT OR IGNORE INTO whatsapp_note_queue
            (message_id,module_name,record_id,group_id,sender_name,group_name,
             message_text,unix_timestamp,display_timestamp,scheduled_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (message_id,module_name,str(record_id),group_id,sender_name,group_name,
             message_text,float(unix_timestamp),display_timestamp,scheduled_at))
        row = conn.execute('''SELECT queue_status,note_id FROM whatsapp_note_queue
            WHERE message_id=? AND module_name=? AND record_id=?''',
            (message_id,module_name,str(record_id))).fetchone()
    return {'status': 'queued' if cursor.rowcount else row['queue_status'],
            'note_id': row['note_id']}


def recover_interrupted_jobs():
    """A crashed worker may have created a Zoho Note; never blindly retry."""
    with _connect() as conn:
        conn.execute('''UPDATE whatsapp_note_queue SET queue_status='reconciliation_required',
            last_error='Worker interrupted; verify Zoho Note before retry',
            updated_at=CURRENT_TIMESTAMP WHERE queue_status='processing' ''')


def claim_next_due_note():
    """One atomic claim, ordered by source timestamp; safe with concurrent workers."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('''SELECT * FROM whatsapp_note_queue q
            WHERE q.queue_status='queued' AND q.scheduled_at<=?
              AND NOT EXISTS (SELECT 1 FROM whatsapp_note_queue earlier
                  WHERE earlier.module_name=q.module_name AND earlier.record_id=q.record_id
                    AND earlier.queue_status IN ('queued','processing','reconciliation_required')
                    AND (earlier.unix_timestamp<q.unix_timestamp OR
                         (earlier.unix_timestamp=q.unix_timestamp AND earlier.message_id<q.message_id)))
            ORDER BY q.unix_timestamp,q.message_id,q.module_name,q.record_id LIMIT 1''', (now,)).fetchone()
        if row is None:
            return None
        conn.execute('''UPDATE whatsapp_note_queue SET queue_status='processing',
            attempt_count=attempt_count+1, updated_at=CURRENT_TIMESTAMP
            WHERE message_id=? AND module_name=? AND record_id=? AND queue_status='queued' ''',
            (row['message_id'],row['module_name'],row['record_id']))
        return dict(row)


def finish_note_job(job, status, note_id=None, error=None):
    if status not in ('completed','reconciliation_required'):
        raise ValueError('Invalid final queue status')
    with _connect() as conn:
        conn.execute('''UPDATE whatsapp_note_queue SET queue_status=?,note_id=?,last_error=?,
            updated_at=CURRENT_TIMESTAMP WHERE message_id=? AND module_name=? AND record_id=?''',
            (status,note_id,error,job['message_id'],job['module_name'],job['record_id']))
