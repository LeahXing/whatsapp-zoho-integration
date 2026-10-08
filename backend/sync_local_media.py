# ============================================================
# Local JSON Data Synchronization Script
# ============================================================

import os
import json
import time
import logging
import requests
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Path to the locally saved JSON record file
JSON_FILE_PATH = os.path.join(config.MEDIA_OUTPUT_DIR, "whatsapp_group_Stock.json")


def sync_local_data():
    """
    Reads local JSON records from disk and posts them sequentially to the
    FastAPI Zoho integration endpoint with a delay to respect API rate limits.
    """
    if not os.path.exists(JSON_FILE_PATH):
        logger.error("JSON file not found at: %s", JSON_FILE_PATH)
        return

    with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    logger.info("Found %d local record(s) to process from %s", len(records), JSON_FILE_PATH)
    headers = {"Content-Type": "application/json"}

    for idx, record in enumerate(records, 1):
        msg_id = record.get("messageId", f"unknown_{idx}")

        # Ensure mediaPath is mapped cleanly if using internal _mediaPath
        if "_mediaPath" in record and not record.get("mediaPath"):
            record["mediaPath"] = record["_mediaPath"]

        logger.info("[%d/%d] Dispatching Message ID: %s", idx, len(records), msg_id)

        try:
            res = requests.post(
                config.ZOHO_INTEGRATION_API_URL,
                json=record,
                headers=headers,
                timeout=100
            )
            if res.status_code in (200, 201):
                logger.info("  ✅ Successfully dispatched to Zoho CRM")
            else:
                logger.error("  ❌ API Error (%d): %s", res.status_code, res.text)
        except Exception as exc:
            logger.error("  ❌ Dispatch exception for Message ID %s: %s", msg_id, exc)

        # 0.6-second delay between dispatches to prevent rate-limiting/lockouts on Zoho OAuth
        time.sleep(0.6)

    logger.info("Sync complete!")


if __name__ == "__main__":
    sync_local_data()