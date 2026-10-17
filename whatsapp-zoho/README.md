# Historical Deal Backfill (incremental patch)

Copy the three files under `app/` into the corresponding project folders.

Add these lines to the existing root `main.py` (do not replace its lifespan):

```python
from app.routes.deal_routes import router as deal_router
app.include_router(deal_router)
```

**Before using:** Confirm your existing `zoho_repository.py` exports `get_headers`, `ZOHO_API_DOMAIN`, `WHATSAPP_MESSAGES_MODULE`, and `DEALS_MODULE` (these were referenced in your pasted code). Confirm Zoho field API names: `Group_ID`, `Message_ID`, `Unix_Timestamp`, `Message`, `Sender_Name`, `Group_Name`, `Deal`.

Restart Uvicorn. Swagger endpoint: `POST /api/v1/deals/{deal_id}/backfill?dry_run=true`.

1. Obtain the actual Zoho Deal ID from its URL or CRM API.
2. Run with `dry_run=true`; review `messages` and `skipped` (especially conflicting Deal links).
3. Run with `dry_run=false` to enqueue Deal Notes using the existing 10-second queue.
4. Check `whatsapp_note_queue` for `module_name='Deals'` and `record_id=<deal_id>`.

**Limitations:** Manual trigger only; no automatic Zoho Deal-created webhook. This patch creates Notes but does not change the WhatsApp_Messages `Deal` lookup. Existing Deal links to other Deals are skipped. Dry run performs Zoho reads but no writes. The queue is idempotent for `(message_id, module_name, record_id)`; it does not reconcile a Note created outside this queue. Zoho Note list sorting is not controlled by this endpoint. The service uses the Deal's stored Date/Time timezone offset.

**Security:** The endpoint has no authentication in this patch. Keep the API localhost-only for development; add your project's authorization before exposing it to other users or networks.
