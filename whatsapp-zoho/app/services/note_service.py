"""Idempotent WhatsApp -> Zoho Note synchronization."""
from datetime import datetime
from app.repositories.zoho_repository import create_zoho_note, get_zoho_notes
from app.storage.processing_state import get_note_sync_state, save_note_sync_state, claim_note_sync


def sync_whatsapp_note(module_name: str, record_id: str, message_id: str,
                       sender_name: str, group_name: str, timestamp: str,
                       message_text: str) -> dict:
    if not message_id or not record_id:
        raise ValueError('message_id and record_id are required')
    state = get_note_sync_state(message_id,module_name,record_id)
    if state and state['sync_status'] == 'completed':
        return {'status':'already_synced','note_id':state['note_id']}

    normalized = str(timestamp or '').strip()
    for fmt in ('%Y-%m-%d %I:%M:%S %p','%Y-%m-%d %H:%M:%S'):
        try:
            normalized = datetime.strptime(normalized,fmt).strftime('%Y-%m-%d %H:%M:%S')
            break
        except ValueError:
            pass
    title = f'{group_name} | {sender_name} | {normalized}'
    marker = f'WhatsApp Message ID: {message_id}'
    content = f'{message_text or ""}\n\n{marker}'

    # Reconcile with Zoho first, including a legacy note without marker.
    notes = get_zoho_notes(module_name=module_name,record_id=record_id)
    matches = [n for n in notes if marker in (n.get('Note_Content') or '')]
    if len(matches) == 1 and matches[0].get('id'):
        note_id = matches[0]['id']
        save_note_sync_state(message_id,module_name,record_id,note_id,'completed')
        return {'status':'already_synced','note_id':note_id}
    if len(matches) > 1:
        return {'status':'reconciliation_required','note_id':None,
                'reason':'Multiple Zoho Notes contain the same message marker'}
    legacy = [n for n in notes if n.get('Note_Title') == title and
              n.get('Note_Content') == (message_text or '')]
    if legacy:
        return {'status':'reconciliation_required',
                'note_id':legacy[0].get('id') if len(legacy)==1 else None,
                'reason':'Legacy Note without Message ID marker; review manually'}
    if state and state['sync_status'] == 'pending':
        return {'status':'reconciliation_required','note_id':state.get('note_id'),
                'reason':'Prior claim exists; Zoho creation outcome may be uncertain'}
    if not claim_note_sync(message_id,module_name,record_id):
        return {'status':'reconciliation_required','note_id':None}
    # Once claimed, failures are uncertain; do not automatically retry create.
    result = create_zoho_note(module_name=module_name,record_id=record_id,
                              note_title=title,note_content=content)
    note_id = result.get('details',{}).get('id')
    if not note_id:
        raise RuntimeError('Zoho Note create returned no ID; reconciliation required')
    save_note_sync_state(message_id,module_name,record_id,note_id,'completed')
    return {'status':'created','note_id':note_id}
