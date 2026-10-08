"""
Configuration Module for WhatsApp Web Scraper.
Defines target groups, date range filters, paths, automation timeouts,
and Zoho Integration API connection settings.
"""

import os
from datetime import date
from typing import List

# Target groups to scrape
TARGET_GROUPS: List[str] = [
    "Stock"
]

TODAY_STR: str = str(date.today().strftime("%Y-%m-%d"))

# Date Range Filter (Format: YYYY-MM-DD)
START_DATE: str = "2026-09-24"
END_DATE: str = TODAY_STR

# File Paths & Storage Settings
EXCEL_FILE: str = "whatsapp_group.xlsx"
USER_DATA_DIR: str = str(os.path.abspath("./whatsapp_user_data"))
MEDIA_OUTPUT_DIR: str = str(os.path.abspath("./downloaded_media"))

# WhatsApp Zoho Integration API Endpoint Settings
# D:\ai_learning\whatsapp_scraper_1\backend\config.py

# Ensure /api/ prefix is present
# D:\ai_learning\whatsapp_scraper_1\backend\config.py

# Ensure /api/ prefix is present
ZOHO_INTEGRATION_API_URL: str = "http://127.0.0.1:8000/api/v1/messages/"

# Extended Automation Timeouts (in milliseconds)
LOGIN_TIMEOUT: int = 3 * 60 * 1000
ELEMENT_TIMEOUT: int = 3 * 60 * 1000
DOWNLOAD_TIMEOUT: int = 1 * 60 * 1000
AUTH_PROBE_TIMEOUT_MS: int = 20 * 1000
MAX_HISTORY_SCROLLS: int = 60

# Media Downloader Specific Timeouts (in milliseconds)
DIRECT_DOWNLOAD_RACE_MS: int = 3000
VIEWER_APPEAR_TIMEOUT_MS: int = 5000
CONTEXT_MENU_TIMEOUT_MS: int = 3000