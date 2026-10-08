"""
Media Downloader Module.
Manages file tracking paths, byte extraction, and duplicate prevention checks.
"""

import os
import re
import base64
import hashlib
import logging
import uuid
import asyncio
from typing import List, Optional, Tuple, Set

from playwright.async_api import (
    ElementHandle,
    Page,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)

try:
    from playwright._impl._errors import TargetClosedError
except ImportError:
    TargetClosedError = PlaywrightError

import config

logger = logging.getLogger(__name__)


# Selectors confirmed by the Phase 0 probes against the live "Stock" group.
CARD_SELECTOR: str = '[data-testid="document-thumb"]'
VIEWER_SELECTOR: str = '[data-testid="media-viewer-modal"]'
VIEWER_DOWNLOAD_SELECTOR: str = '[data-testid="media-viewer-modal"] [aria-label="Download"]'

# Non-previewable documents expose Download only through the card's right-click
# menu - a plain left-click on them is measurably inert (no viewer, no download).
CONTEXT_MENU_DOWNLOAD_SELECTOR: str = (
    '[role="menu"] [aria-label="Download"], '
    '[role="menuitem"][aria-label="Download"], '
    'li[aria-label="Download"]'
)


class WhatsAppMediaDownloader:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.media_hashes: Set[str] = set()

    def get_safe_filename(self, media_name: str, message_id: str, extension: str, group_name: str) -> Tuple[str, str]:
        """Generates a structured directory and file pathway tracking references cleanly."""
        clean_folder = "".join(c for c in group_name if c.isalnum() or c in (' ', '_')).rstrip()
        group_folder = os.path.join(config.MEDIA_OUTPUT_DIR, clean_folder.replace(" ", "_"))
        os.makedirs(group_folder, exist_ok=True)

        safe_media_name = "".join(c for c in (media_name or "file") if c.isalnum() or c in ('_', '-')).strip()
        if not safe_media_name:
            safe_media_name = f"media_{uuid.uuid4().hex[:6]}"

        safe_msg_id = "".join(c for c in (message_id or uuid.uuid4().hex[:8]) if c.isalnum() or c in ('_', '-')).strip()
        
        file_name = f"{safe_media_name}_{safe_msg_id}.{extension}"
        file_path = os.path.join(group_folder, file_name)
        return group_folder, file_path

    def verify_or_store_hash(self, file_path: str, binary_data: bytes) -> bool:
        """Computes message MD5 checksum arrays. Returns True if file content is already duplicate."""
        file_hash = hashlib.md5(binary_data).hexdigest()
        if file_hash in self.media_hashes:
            return True
        self.media_hashes.add(file_hash)
        return False

    async def download_media_file_async(self, element: ElementHandle, extension: str, group_name: str, media_name: str, message_id: str) -> str:
        """Extracts simple images or embedded elements with basic javascript base64 streaming overrides."""
        _, file_path = self.get_safe_filename(media_name, message_id, extension, group_name)

        if os.path.exists(file_path):
            return file_path

        try:
            if self.page.is_closed():
                return "[Media Download Failed]"

            await element.scroll_into_view_if_needed()
            await asyncio.sleep(0.2)

            js_code = """
            async (el) => {
                try {
                    let targetUrl = el.src || el.href;
                    if (!targetUrl && el.querySelector('img')) targetUrl = el.querySelector('img').src;
                    if (!targetUrl && el.querySelector('video')) targetUrl = el.querySelector('video').src;
                    if (!targetUrl) return null;
                    if (targetUrl.startsWith('data:')) return targetUrl.split(',')[1];

                    const res = await fetch(targetUrl);
                    const blob = await res.blob();
                    return await new Promise((resolve) => {
                        const reader = new FileReader();
                        reader.onloadend = () => resolve(reader.result.split(',')[1]);
                        reader.onerror = () => resolve(null);
                        reader.readAsDataURL(blob);
                    });
                } catch (e) { return null; }
            }
            """
            base64_data = await self.page.evaluate(js_code, element)
            if base64_data:
                binary_data = base64.b64decode(base64_data)
                if self.verify_or_store_hash(file_path, binary_data):
                    return file_path

                with open(file_path, "wb") as f:
                    f.write(binary_data)
                return file_path
        except TargetClosedError:
            logger.error("Target closed during inline extraction for '%s' (msg %s)", media_name, message_id)
        except Exception as exc:
            logger.exception("Inline extraction failed for '%s' (msg %s): %s", media_name, message_id, exc)
        return "[Media Download Failed]"

    async def _resolve_document_name(self, doc_el: ElementHandle) -> Tuple[str, str]:
        """Resolves the real filename and extension for a document card."""
        candidates: List[str] = []

        try:
            card_title = await doc_el.get_attribute("title")
            if card_title:
                match = re.search(r'"([^"]+)"', card_title)
                if match:
                    candidates.append(match.group(1).strip())

            title_el = await doc_el.query_selector("span[title]")
            if title_el:
                span_title = await title_el.get_attribute("title")
                if span_title and "." in span_title:
                    candidates.append(span_title.strip())

            candidates.append((await doc_el.get_attribute("download")) or "")
        except TargetClosedError:
            logger.error("Page closed while resolving document name.")

        name = next((c for c in candidates if c and "." in c), "Document Attachment")

        ext = name.split(".")[-1].strip().lower() if "." in name else "pdf"
        if len(ext) > 5 or not ext.isalnum():
            ext = "pdf"
        return name, ext

    async def _find_context_menu_download(self) -> Optional[ElementHandle]:
        """Locates the Download entry in a document card's right-click menu."""
        if self.page.is_closed():
            return None
        try:
            timeout_ms = getattr(config, "CONTEXT_MENU_TIMEOUT_MS", 3000)
            return await self.page.wait_for_selector(
                CONTEXT_MENU_DOWNLOAD_SELECTOR, timeout=timeout_ms
            )
        except PlaywrightTimeoutError:
            logger.debug("Scoped context-menu selector missed; trying a bare aria-label lookup.")
        except TargetClosedError:
            logger.error("Target page closed during context menu lookup.")
            return None

        try:
            if not self.page.is_closed():
                timeout_ms = getattr(config, "CONTEXT_MENU_TIMEOUT_MS", 3000)
                return await self.page.wait_for_selector(
                    '[aria-label="Download"]', timeout=timeout_ms
                )
        except (PlaywrightTimeoutError, TargetClosedError):
            pass
        return None

    async def _dismiss_menu(self) -> None:
        """Dismisses any open context menu so it cannot cover the next row."""
        try:
            if not self.page.is_closed():
                await self.page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
        except TargetClosedError:
            pass
        except Exception as exc:
            logger.warning("Could not dismiss context menu: %s", exc)

    async def _close_viewer(self) -> None:
        """Dismisses the media viewer safely."""
        try:
            if self.page.is_closed():
                return
            close_btn = await self.page.query_selector(f'{VIEWER_SELECTOR} [aria-label="Close"]')
            if close_btn:
                await close_btn.click()
            else:
                await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
        except TargetClosedError:
            pass
        except Exception as exc:
            logger.warning("Could not close media viewer: %s", exc)

    async def _extract_inline_blob(self, element: ElementHandle, file_path: str) -> str:
        """Pulls bytes straight out of an inline blob/data URI with TargetClosedError guards."""
        js_code = """
        async (el) => {
            try {
                let targetUrl = el.src || el.href;
                if (!targetUrl && el.querySelector('img')) targetUrl = el.querySelector('img').src;
                if (!targetUrl) {
                    const a = el.querySelector('a[href]');
                    if (a) targetUrl = a.href;
                }
                if (!targetUrl) return null;
                if (targetUrl.startsWith('data:')) return targetUrl.split(',')[1];

                const res = await fetch(targetUrl);
                const blob = await res.blob();
                return await new Promise((resolve) => {
                    const reader = new FileReader();
                    reader.onloadend = () => resolve(reader.result.split(',')[1]);
                    reader.onerror = () => resolve(null);
                    reader.readAsDataURL(blob);
                });
            } catch (e) { return null; }
        }
        """
        try:
            if self.page.is_closed():
                return ""
            base64_data = await self.page.evaluate(js_code, element)
            if not base64_data:
                return ""
            binary_data = base64.b64decode(base64_data)
            if self.verify_or_store_hash(file_path, binary_data):
                return file_path
            with open(file_path, "wb") as f:
                f.write(binary_data)
            logger.info("Blob fallback OK: %s", file_path)
            return file_path
        except TargetClosedError:
            logger.error("Blob fallback aborted: Target page closed for %s", file_path)
            return ""
        except Exception as exc:
            logger.exception("Blob fallback failed for %s: %s", file_path, exc)
            return ""

    async def detect_and_download_attachments(self, row: ElementHandle, group_name: str, message_id: str) -> Tuple[str, str, str]:
        """Orchestrates structural processing variables for PDFs, files, pictures, or voice notes."""
        media_type = "chat"
        media_name = ""
        file_path = ""

        try:
            if self.page.is_closed():
                return media_type, media_name, "[Media Download Failed]"

            # 1. Document Extraction Block
            card = await row.query_selector(CARD_SELECTOR)
            doc_el = card or await row.query_selector(
                "div[title], a[download], [aria-label*='document'], [aria-label*='file'], [data-testid='document-container']"
            )
            if doc_el:
                media_type = "document"
                media_name, ext = await self._resolve_document_name(doc_el)
                _, target_file_path = self.get_safe_filename(media_name, message_id, ext, group_name)

                if os.path.exists(target_file_path):
                    return media_type, media_name, target_file_path

                try:
                    await doc_el.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)
                except (PlaywrightError, TargetClosedError) as exc:
                    logger.warning(
                        "Document element detached before download for '%s' (msg %s): %s",
                        media_name, message_id, exc,
                    )
                    return media_type, media_name, "[Media Download Failed]"

                target = await doc_el.query_selector(CARD_SELECTOR) or doc_el

                try:
                    # STEP 1 - Direct Download Race using config.DIRECT_DOWNLOAD_RACE_MS
                    direct_race_ms = getattr(config, "DIRECT_DOWNLOAD_RACE_MS", 3000)
                    try:
                        async with self.page.expect_download(timeout=direct_race_ms) as direct:
                            await target.click()
                        download = await direct.value
                        await download.save_as(target_file_path)
                        logger.info("Direct download OK: '%s' -> %s", media_name, target_file_path)
                        return media_type, media_name, target_file_path
                    except PlaywrightTimeoutError:
                        pass

                    # STEP 2 - Media Viewer Download using config.VIEWER_APPEAR_TIMEOUT_MS
                    viewer_opened = False
                    viewer_timeout_ms = getattr(config, "VIEWER_APPEAR_TIMEOUT_MS", 5000)
                    try:
                        if not self.page.is_closed():
                            await self.page.wait_for_selector(VIEWER_SELECTOR, timeout=viewer_timeout_ms)
                            viewer_opened = True
                    except (PlaywrightTimeoutError, TargetClosedError):
                        pass

                    if viewer_opened and not self.page.is_closed():
                        download_btn = await self.page.wait_for_selector(
                            VIEWER_DOWNLOAD_SELECTOR, timeout=config.DOWNLOAD_TIMEOUT
                        )
                        async with self.page.expect_download(timeout=config.DOWNLOAD_TIMEOUT) as viewer_dl:
                            await download_btn.click()
                        download = await viewer_dl.value
                        await download.save_as(target_file_path)
                        logger.info("Viewer download OK: '%s' -> %s", media_name, target_file_path)
                        await self._close_viewer()
                        return media_type, media_name, target_file_path

                    # STEP 3 - Context Menu Download
                    if not self.page.is_closed():
                        try:
                            await target.click(button="right")
                            menu_btn = await self._find_context_menu_download()
                            if menu_btn is not None and not self.page.is_closed():
                                async with self.page.expect_download(timeout=config.DOWNLOAD_TIMEOUT) as menu_dl:
                                    await menu_btn.click()
                                download = await menu_dl.value
                                await download.save_as(target_file_path)
                                logger.info("Context-menu download OK: '%s' -> %s", media_name, target_file_path)
                                return media_type, media_name, target_file_path
                            logger.warning(
                                "Context-menu Download item not found for '%s' (msg %s)", media_name, message_id
                            )
                        finally:
                            await self._dismiss_menu()

                except TargetClosedError:
                    logger.error("Target closed during download process for '%s' (msg %s)", media_name, message_id)
                except PlaywrightTimeoutError:
                    logger.warning("Document download timed out for '%s' (msg %s)", media_name, message_id)
                    await self._close_viewer()
                except Exception as exc:
                    logger.exception("Document download error for '%s' (msg %s): %s", media_name, message_id, exc)
                    await self._close_viewer()

                # STEP 4 - Inline Blob Fallback
                blob_path = await self._extract_inline_blob(doc_el, target_file_path)
                if blob_path:
                    return media_type, media_name, blob_path

                return media_type, media_name, "[Media Download Failed]"

            # 2. Image Extraction Block
            img_el = await row.query_selector("img[src]")
            if img_el:
                src = await img_el.get_attribute("src") or ""
                alt = await img_el.get_attribute("alt") or ""
                if src and not any(k in src.lower() for k in ["emoji", "avatar", "pp-", "user-"]):
                    media_type = "image"
                    media_name = alt or "Image Attachment"
                    file_path = await self.download_media_file_async(img_el, "jpg", group_name, media_name, message_id)
                    return media_type, media_name, file_path

            # 3. Video Extraction Block
            video_el = await row.query_selector("video")
            if video_el:
                media_type = "video"
                media_name = "Video Attachment"
                file_path = await self.download_media_file_async(video_el, "mp4", group_name, media_name, message_id)
                return media_type, media_name, file_path

        except TargetClosedError:
            logger.error("Target closed during attachment detection for msg %s", message_id)
        except Exception as exc:
            logger.exception("Attachment detection failed for msg %s: %s", message_id, exc)
            
        return media_type, media_name, file_path