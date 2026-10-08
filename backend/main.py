"""
Main Execution Script (Direct Production Layout).
Bypasses the unpredictable landing homepage entirely to deep-link directly into 
the WhatsApp Web workspace with stealth security spoofing arguments.
"""

import os
import sys
import json
import asyncio
import requests
from typing import List, Dict, Any

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore

from playwright.async_api import async_playwright
from chat_scraper import WhatsAppScraperAsync
from excel_exporter import ExcelExporter
from logger import setup_logging
import config

USER_DATA_DIR = config.USER_DATA_DIR
OUTPUT_DIR = config.MEDIA_OUTPUT_DIR

# A valid session renders almost immediately, so this probe stays short: a
# logged-out run should reach the QR prompt quickly rather than stalling silently.
AUTH_PROBE_TIMEOUT_MS: int = getattr(config, "AUTH_PROBE_TIMEOUT_MS", 20_000)

# WhatsApp Zoho Integration API Endpoint URL retrieved directly from config
ZOHO_INTEGRATION_API_URL = getattr(
    config, 
    "ZOHO_INTEGRATION_API_URL", 
    "http://127.0.0.1:8000/api/whatsapp-messages"
)


def send_records_to_zoho_api(data: List[Dict[str, Any]]) -> None:
    """
    Path Mapping & API Dispatch:
    Maps the local directory path (_mediaPath) to mediaPath inside each JSON record
    and POSTs each payload to the WhatsApp Zoho Integration API endpoint.
    """
    if not data:
        return

    print(f"\n 📤 Dispatching {len(data)} message record(s) to Zoho Integration API: '{ZOHO_INTEGRATION_API_URL}'...")
    headers = {"Content-Type": "application/json"}
    success_count = 0
    failed_count = 0

    for record in data:
        # Path Mapping: ensure local media directory path is stored under mediaPath
        media_path = record.get("_mediaPath")
        if media_path and media_path != "[Media Download Failed]":
            record["mediaPath"] = media_path

        # API Dispatch
        try:
            response = requests.post(
                ZOHO_INTEGRATION_API_URL, 
                json=record, 
                headers=headers, 
                timeout=15
            )

            if response.status_code in (200, 201):
                res_data = response.json()
                if res_data.get("status") == "duplicate":
                    print(f"  ℹ️ Duplicate message ignored (Message ID: {record.get('messageId')})")
                else:
                    print(f"  ✅ Successfully dispatched Message ID: {record.get('messageId')}")
                success_count += 1
            else:
                print(f"  ❌ API returned status {response.status_code} for Message ID {record.get('messageId')}: {response.text}")
                failed_count += 1

        except Exception as e:
            print(f"  ❌ Failed to dispatch Message ID {record.get('messageId')}: {e}")
            failed_count += 1

    print(f" 📊 Dispatch complete: {success_count} succeeded, {failed_count} failed.\n")


def save_group_outputs(group_name: str, data: List[Dict[str, Any]]) -> None:
    """Saves date-filtered payloads into JSON arrays, dispatches to Zoho API, and writes Excel workbooks."""
    if not data:
        print(f" ⚠️ No date-matching data to save for group '{group_name}'.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    clean_group_name = "".join(c for c in group_name if c.isalnum() or c in (' ', '_')).strip().replace(" ", "_")
    base_filename = f"whatsapp_group_{clean_group_name}"

    # 1. Save JSON
    json_filename = os.path.join(OUTPUT_DIR, f"{base_filename}.json")
    try:
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f" 💾 Saved matching records to JSON: '{json_filename}'")
    except Exception as e:
        print(f" ❌ Failed to save JSON for {group_name}: {e}")

    # 2. Path Mapping & API Dispatch to WhatsApp Zoho Integration API
    send_records_to_zoho_api(data)

    # 3. Save Styled Excel Worksheet
    excel_filename = os.path.join(OUTPUT_DIR, f"{base_filename}.xlsx")
    group_data_dict = {group_name: data}

    try:
        ExcelExporter.save_to_excel(group_data_dict, excel_filename)
        print(f" 📊 Excel export completed successfully: '{excel_filename}'")
    except Exception as e:
        print(f"\n ❌ Excel export failed for {group_name}: {e}\n")

    # 4. Report attachment failures so a run cannot claim success while silently
    #    dropping downloads.
    failed_media = [
        record for record in data
        if record.get("messageContent", {}).get("hasMediaAttached")
        and (not record.get("_mediaPath") or record.get("_mediaPath") == "[Media Download Failed]")
    ]
    if failed_media:
        print(f" ⚠️ {len(failed_media)} attachment(s) FAILED to download:")
        for record in failed_media:
            media_type = record.get("messageMeta", {}).get("messageType")
            print(f"      - {record.get('messageId')} ({media_type})")
    else:
        print(" ✅ All attachments downloaded successfully.")


async def main() -> None:
    """Launches the browser context directly to WhatsApp Web using stability user-agent parameters."""
    setup_logging()
    print("🚀 Starting Production WhatsApp Data Extraction Service...")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            accept_downloads=True,
            # Strict layout arguments to avoid triggering "Browser not supported" checkpoints
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                # Bypasses internal automation markers that flag the browser context
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ],
            no_viewport=True,
            # Forces an explicit, modern browser identification header string
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        page = context.pages[0] if context.pages else await context.new_page()
        
        # --- DIRECT PRODUCTION ROUTING ---
        print("🌐 Navigating directly to WhatsApp Web Core Interface...")
        await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
        
        print("⏳ Waiting for interface components to render...")
        try:
            # Monitors the chat search element which guarantees successful login/session load
            await page.wait_for_selector('#pane-side', timeout=AUTH_PROBE_TIMEOUT_MS)
            print(" ✅ Authenticated session verified successfully.")
        except Exception:
            print(
                " ⚠️ QR Code scanning checkpoint active. "
                f"Scan the QR code via phone within {config.LOGIN_TIMEOUT // 60000} minutes."
            )
            try:
                await page.wait_for_selector('#pane-side', timeout=config.LOGIN_TIMEOUT)
                print(" ✅ Authentication successful!")
            except Exception:
                print(" ❌ Authentication checkpoint timed out. Closing browser process pipeline...")
                await context.close()
                return

        # Core operational tracking objects initialization
        scraper = WhatsAppScraperAsync(page)
        # Automatically detect the logged-in WhatsApp account name
        try:
            # Open account settings
            await page.locator('button[aria-label="You"]').click()

            # Open Edit profile
            await page.locator('text="Profile"').click()

            # Read the profile name
            profile_name = await page.locator(
                '[data-testid="pushname-input-read-only selectable-text"]'
            ).inner_text(timeout=5000)

            scraper.current_user_name = profile_name.strip()

            print(f"✅ Logged-in WhatsApp user: {scraper.current_user_name}")
            # Return to the main WhatsApp chat interface
            await page.reload(wait_until="domcontentloaded")
            await page.wait_for_selector('#pane-side', timeout=30000)


        except Exception as exc:
            print(f"⚠️ WhatsApp profile name not detected: {exc}")

        target_groups = getattr(config, "TARGET_GROUPS", ["Stock"])

        for group_name in target_groups:
            print(f"\n" + "-"*50)
            print(f" 🎯 Processing Target Chat Panel: '{group_name}'")
            print(f"-"*50)

            opened = await scraper.open_group(group_name)
            if opened:
                group_messages = await scraper.scrape_active_chat(group_name)
                if group_messages:
                    save_group_outputs(group_name, group_messages)
                else:
                    print(f" ℹ️ No workspace logs matched date configurations for '{group_name}'.")
            else:
                print(f" ❌ Skipping '{group_name}' (Could not expand chat pane selectors).")

            await asyncio.sleep(2)

        print("\n 🎉 Extraction process finished. Shutting down browser context safely...")
        await context.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n 🛑 Execution stopped by user request.")