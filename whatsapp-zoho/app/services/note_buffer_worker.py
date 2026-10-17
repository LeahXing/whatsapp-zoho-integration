"""Single background thread for durable, buffered Zoho Notes synchronization."""
import logging
import threading
from app.storage.processing_state import (
    claim_next_due_note, finish_note_job, recover_interrupted_jobs,
)
from app.services.note_service import sync_whatsapp_note

log = logging.getLogger(__name__)
_stop = threading.Event()
_thread = None


def _run():
    while not _stop.is_set():
        try:
            job = claim_next_due_note()
            if not job:
                _stop.wait(0.5)
                continue
            try:
                result = sync_whatsapp_note(
                    module_name=job['module_name'], record_id=job['record_id'],
                    message_id=job['message_id'], sender_name=job['sender_name'] or 'Unknown',
                    group_name=job['group_name'] or 'Unknown Group',
                    timestamp=job['display_timestamp'], message_text=job['message_text'] or '')
                status = result.get('status')
                if status in ('created','already_synced'):
                    finish_note_job(job,'completed',note_id=result.get('note_id'))
                else:
                    finish_note_job(job,'reconciliation_required',
                                    note_id=result.get('note_id'),error=result.get('reason') or status)
            except Exception as exc:
                log.exception('Note sync requires reconciliation: %s', job['message_id'])
                finish_note_job(job,'reconciliation_required',error=str(exc))
        except Exception:
            log.exception('Notes worker loop error')
            _stop.wait(2)


def start_note_buffer_worker():
    global _thread
    if _thread and _thread.is_alive():
        return
    recover_interrupted_jobs()
    _stop.clear()
    _thread = threading.Thread(target=_run, name='zoho-notes-worker',daemon=True)
    _thread.start()


def stop_note_buffer_worker():
    global _thread
    _stop.set()
    if _thread:
        _thread.join(timeout=20)
        if _thread.is_alive():
            log.warning('Notes worker still running; unfinished job will require reconciliation')
        _thread = None
