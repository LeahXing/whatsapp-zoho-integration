import csv
from collections import Counter

import requests

from app.repositories.zoho_repository import (
    ZOHO_API_DOMAIN,
    WHATSAPP_MESSAGES_MODULE,
    get_headers,
    get_zoho_notes,
    find_contact_by_whatsapp_id,
    find_lead_by_whatsapp_id,
)
from app.storage.processing_state import get_note_sync_state


FIELDS = (
    "Message_ID,Group_Name,Sender_Name,WhatsApp_ID,"
    "Display_Date,Display_Time,Message,Contact,Lead,Deal"
)

REPORT_PATH = "whatsapp_history_migration_preview.csv"


def lookup_id(value):
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return str(value or "")


def fetch_messages():
    records = []
    page = 1

    while True:
        response = requests.get(
            f"{ZOHO_API_DOMAIN}/crm/v8/{WHATSAPP_MESSAGES_MODULE}",
            headers=get_headers(),
            params={
                "fields": FIELDS,
                "per_page": 200,
                "page": page,
            },
            timeout=30,
        )

        if response.status_code == 204:
            break

        response.raise_for_status()
        result = response.json()
        records.extend(result.get("data", []))

        if not result.get("info", {}).get("more_records", False):
            break

        page += 1

    return records


def main():
    messages = fetch_messages()
    sender_cache = {}
    notes_cache = {}
    report = []
    summary = Counter()

    for message in messages:
        message_id = str(message.get("Message_ID") or "")
        whatsapp_id = str(message.get("WhatsApp_ID") or "")
        group = str(message.get("Group_Name") or "")
        sender = str(message.get("Sender_Name") or "")
        date = str(message.get("Display_Date") or "")
        time = str(message.get("Display_Time") or "")
        content = message.get("Message") or ""

        # Preserve the display time as recorded in Zoho.
        timestamp = f"{date} {time}".strip()
        title = f"{group} | {sender} | {timestamp}"

        destinations = []
        for field, module in (
            ("Contact", "Contacts"),
            ("Lead", "Leads"),
            ("Deal", "Deals"),
        ):
            record_id = lookup_id(message.get(field))
            if record_id:
                destinations.append((module, record_id))

        resolution = "stored_relationship"

        if not destinations:
            resolution = "whatsapp_id_lookup"

            if whatsapp_id not in sender_cache:
                contact = (
                    find_contact_by_whatsapp_id(whatsapp_id)
                    if whatsapp_id else None
                )
                lead = (
                    find_lead_by_whatsapp_id(whatsapp_id)
                    if whatsapp_id else None
                )
                sender_cache[whatsapp_id] = (contact, lead)

            contact, lead = sender_cache[whatsapp_id]

            if contact and lead:
                resolution = "ambiguous_sender"
            elif contact:
                destinations = [("Contacts", str(contact["id"]))]
            elif lead:
                destinations = [("Leads", str(lead["id"]))]
            else:
                resolution = "unmatched_sender"

        if not destinations:
            report.append({
                "message_id": message_id,
                "sender": sender,
                "module": "",
                "record_id": "",
                "status": "REVIEW",
                "reason": resolution,
                "note_title": title,
            })
            summary["REVIEW"] += 1
            continue

        for module, record_id in destinations:
            status = "READY"
            reason = resolution

            if module == "Leads" and whatsapp_id:
                if whatsapp_id not in sender_cache:
                    sender_cache[whatsapp_id] = (
                        find_contact_by_whatsapp_id(whatsapp_id),
                        None,
                    )

                matched_contact = sender_cache[whatsapp_id][0]

                if matched_contact:
                    module = "Contacts"
                    record_id = str(matched_contact["id"])
                    reason = "contact_match_for_historical_lead"

            if not message_id or not content:
                status = "REVIEW"
                reason = "missing_message_id_or_content"
            else:
                state = get_note_sync_state(
                    message_id=message_id,
                    module_name=module,
                    record_id=record_id,
                )

                if state:
                    if state["sync_status"] == "completed":
                        status = "ALREADY_TRACKED"
                        reason = "sqlite_completed"
                    else:
                        status = "REVIEW"
                        reason = "sqlite_pending"

                if status == "READY":
                    cache_key = (module, record_id)

                    if cache_key not in notes_cache:
                        try:
                            notes_cache[cache_key] = get_zoho_notes(
                                module_name=module,
                                record_id=record_id,
                            )
                        except Exception as exc:
                            notes_cache[cache_key] = None
                            print(
                                "Notes lookup failed:",
                                module, record_id, str(exc)[:200]
                            )

                    notes = notes_cache[cache_key]

                    if notes is None:
                        status = "REVIEW"
                        reason = "notes_lookup_failed"
                    else:
                        legacy_marker = (
                            f"WhatsApp Message ID: {message_id}"
                        )

                        legacy_matches = [
                            note for note in notes
                            if legacy_marker in (
                                note.get("Note_Content") or ""
                            )
                        ]

                        clean_matches = [
                            note for note in notes
                            if note.get("Note_Title") == title
                            and note.get("Note_Content") == content
                        ]

                        if legacy_matches:
                            status = "EXISTING_NOTE"
                            reason = "legacy_message_id_match"
                        elif clean_matches:
                            status = "REVIEW"
                            reason = "possible_clean_note_duplicate"

            report.append({
                "message_id": message_id,
                "sender": sender,
                "module": module,
                "record_id": record_id,
                "status": status,
                "reason": reason,
                "note_title": title,
            })
            summary[status] += 1

    columns = [
        "message_id",
        "sender",
        "module",
        "record_id",
        "status",
        "reason",
        "note_title",
    ]

    with open(REPORT_PATH, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(report)

    print("\nHISTORICAL NOTES MIGRATION PREVIEW")
    print("WhatsApp messages:", len(messages))
    print("Destination rows:", len(report))

    for status in (
        "READY",
        "EXISTING_NOTE",
        "ALREADY_TRACKED",
        "REVIEW",
    ):
        print(f"{status}: {summary[status]}")

    print("Report:", REPORT_PATH)
    print("READ-ONLY: No Zoho Notes were created.")


if __name__ == "__main__":
    main()
