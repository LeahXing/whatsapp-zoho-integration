"""Read-only Zoho queries for historical Deal backfill."""
import requests
from app.repositories.zoho_repository import get_headers, ZOHO_API_DOMAIN, WHATSAPP_MESSAGES_MODULE, DEALS_MODULE


def get_deal_for_backfill(deal_id: str) -> dict:
    response = requests.get(f'{ZOHO_API_DOMAIN}/crm/v8/{DEALS_MODULE}/{deal_id}', headers=get_headers(), timeout=30)
    response.raise_for_status()
    data = response.json().get('data') or []
    if not data:
        raise ValueError(f'Deal {deal_id} not found')
    return data[0]


def find_group_messages_for_backfill(group_id: str) -> list:
    """Search by group, not Deal, so pre-Deal and other senders' messages are included."""
    if not group_id or any(ch in group_id for ch in '(),'):
        raise ValueError('Invalid WhatsApp group ID')
    result = []
    page = 1
    while True:
        response = requests.get(
            f'{ZOHO_API_DOMAIN}/crm/v8/{WHATSAPP_MESSAGES_MODULE}/search',
            headers=get_headers(),
            params={'criteria': f'(Group_ID:equals:{group_id})', 'page': page, 'per_page': 200},
            timeout=30,
        )
        if response.status_code == 204:
            break
        response.raise_for_status()
        body = response.json()
        result.extend(body.get('data') or [])
        if not body.get('info', {}).get('more_records', False):
            break
        page += 1
        if page > 100:
            raise RuntimeError('Backfill search exceeded 100 pages; refusing incomplete backfill')
    return result
