"""
Shared WhatsApp conversation history sorting.

Sorts existing formatted messages chronologically.
Preserves original text and stable order for equal timestamps.
"""

import re
from datetime import datetime


HEADER_PATTERN = re.compile(
    r"^.+ \| (\d{4}-\d{2}-\d{2} "
    r"\d{2}:\d{2}:\d{2} [AP]M)$"
)


def append_conversation_history(existing_history, new_entry):
    if not existing_history:
        return new_entry
    return existing_history.rstrip() + "\n\n" + new_entry


def format_sorted_message_history(records: list) -> str:
    """
    Build chronological conversation history from structured
    Zoho WhatsApp_Messages records.

    Preserves multiline messages and quoted text.
    Does not modify Zoho CRM.
    """

    sorted_records = sorted(
        records,
        key=lambda record: (
            int(record.get("Unix_Timestamp") or 0),
            str(record.get("Message_ID") or "")
        )
    )

    entries = []

    for record in sorted_records:
        sender_name = (
            record.get("Sender_Name")
            or record.get("WhatsApp_ID")
            or "Unknown Sender"
        )

        display_date = record.get("Display_Date") or ""
        display_time = record.get("Display_Time") or ""
        message_text = record.get("Message") or ""

        timestamp = " ".join(
            value
            for value in [display_date, display_time]
            if value
        )

        header = (
            f"{sender_name} | {timestamp}"
            if timestamp
            else sender_name
        )

        entries.append(f"{header}\n{message_text}")

    return "\n\n".join(entries)