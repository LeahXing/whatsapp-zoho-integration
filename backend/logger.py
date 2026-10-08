"""
Centralized logging configuration for the WhatsApp scraper.

Provides console output plus a rotating file log (`scraper.log`) so that no
failure is ever swallowed silently, as required by the project specification.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

LOG_FILE_NAME: str = "scraper.log"
LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
MAX_BYTES: int = 2 * 1024 * 1024
BACKUP_COUNT: int = 3

_CONFIGURED: bool = False


def _make_formatter() -> logging.Formatter:
    """Builds the shared formatter used by every handler."""
    return logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)


def _build_console_handler() -> logging.StreamHandler:
    """Creates the console handler, tolerating non-UTF-8 Windows consoles."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_make_formatter())
    return handler


def setup_logging(log_dir: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """Configures root logging once and returns the scraper's logger.

    Idempotent: repeated calls will not stack duplicate handlers, so it is safe
    to invoke from any entry point. File logging is best-effort — if the log
    directory cannot be written, the scraper continues with console output only.

    Args:
        log_dir: Directory that receives `scraper.log`. Defaults to this module's
            own directory (the `backend/` package root).
        level: Root logging level.

    Returns:
        The `whatsapp_scraper` logger.
    """
    global _CONFIGURED

    module_logger = logging.getLogger("whatsapp_scraper")
    if _CONFIGURED:
        return module_logger

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(_build_console_handler())

    target_dir = log_dir or os.path.dirname(os.path.abspath(__file__))
    try:
        os.makedirs(target_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(target_dir, LOG_FILE_NAME),
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(_make_formatter())
        root.addHandler(file_handler)
    except OSError as exc:
        module_logger.warning("File logging disabled (%s); console output only.", exc)

    _CONFIGURED = True
    module_logger.debug("Logging initialised (level=%s, dir=%s).", level, target_dir)
    return module_logger
