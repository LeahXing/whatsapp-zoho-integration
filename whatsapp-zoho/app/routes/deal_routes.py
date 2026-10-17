"""Manually triggered historical Deal backfill; default is read-only preview."""
from fastapi import APIRouter, HTTPException, Query
from app.services.deal_backfill_service import preview_or_backfill

router = APIRouter(prefix='/api/v1/deals', tags=['Deal Backfill'])


@router.post('/{deal_id}/backfill')
def backfill_deal(deal_id: str, dry_run: bool = Query(True, description='True: preview only; False: enqueue Deal Notes')):
    try:
        return preview_or_backfill(deal_id, dry_run=dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
