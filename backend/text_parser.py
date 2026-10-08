"""
Text Parser Module.
Processes raw metadata string blocks to isolate clean AM/PM times, dates, and senders.
"""

from datetime import datetime
from typing import Tuple, Optional
import dateutil.parser


class WhatsAppTextParser:
    @staticmethod
    def parse_timestamp(raw_meta: Optional[str]) -> Tuple[str, str, Optional[datetime]]:
        """
        Parses raw text meta strings to extract timestamps, senders, and datetime instances.
        
        Example Input: "[10:42 AM, 10/01/2026] Chatbot Name:"
        """
        if not raw_meta:
            return "", "", None

        try:
            clean_meta = raw_meta.strip()

            if clean_meta.startswith("[") and "]" in clean_meta:
                timestamp_str, sender_part = clean_meta[1:].split("]", 1)
                sender = sender_part.strip().rstrip(":").strip()
            else:
                timestamp_str = clean_meta
                sender = ""

            parsed_dt = dateutil.parser.parse(
                timestamp_str,
                fuzzy=False,
                dayfirst=False
            )

            return timestamp_str, sender, parsed_dt

        except (ValueError, TypeError, OverflowError):
            return raw_meta or "", "", None
