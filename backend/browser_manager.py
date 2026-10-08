"""
Browser Manager Module.
Handles Playwright Chromium synchronous session initialization, persistent login state,
and graceful shutdowns[cite: 1].
"""

import os
from typing import Optional
from playwright.sync_api import sync_playwright, Playwright, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError
import config


class BrowserManager:
    """Manages the lifecycle of the Playwright browser session for WhatsApp Web[cite: 1]."""

    def __init__(self) -> None:
        """Initializes browser manager references[cite: 1]."""
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def start_session(self) -> Optional[Page]:
        """
        Launches Chromium with persistent storage to maintain login state[cite: 1].

        Returns:
            Optional[Page]: The active Playwright browser page instance or None if failed.
        """
        self.playwright = sync_playwright().start()
        os.makedirs(config.USER_DATA_DIR, exist_ok=True)

        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=config.USER_DATA_DIR,
                headless=False,
                no_viewport=True,
                args=["--start-maximized"]
            )
        except Exception as e:
            print(f"❌ Failed to launch browser context: {e}")
            print("👉 Close active Chrome processes or clear the 'whatsapp_session' directory.")
            self.close_session()
            return None

        if len(self.context.pages) > 0:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        self.page.goto("https://web.whatsapp.com")
        
        print("\n=======================================================")
        print("  WhatsApp Web Automation Session")
        print("=======================================================")
        print("Waiting for WhatsApp Web to load...")
        print("👉 Scan the QR Code if prompted.")

        try:
            self.page.wait_for_selector('div[contenteditable="true"]', timeout=config.LOGIN_TIMEOUT)
            print("✅ Successfully authenticated!\n")
            return self.page
        except PlaywrightTimeoutError:
            print("❌ Authentication timed out. Please try again.")
            self.close_session()
            return None

    def close_session(self) -> None:
        """Safely shuts down browser instances and stops Playwright[cite: 1]."""
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()