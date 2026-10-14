import requests

from app.repositories.zoho_repository import (
    ZOHO_API_DOMAIN,
    WHATSAPP_MESSAGES_MODULE,
    get_headers,
)

from app.repositories.zoho_repository import (
    find_contact_by_whatsapp_id,
    find_lead_by_whatsapp_id,
)

def preview_historical_messages():
    url = (
        f"{ZOHO_API_DOMAIN}/crm/v8/"
        f"{WHATSAPP_MESSAGES_MODULE}"
    )

    params = {
        "fields": (
            "Message_ID,Group_Name,Sender_Name,"
            "Display_Date,Display_Time,Message,"
            "Contact,Lead,Deal,WhatsApp_ID"
        ),
        "per_page": 10,
        "page": 1,
    }

    response = requests.get(
        url,
        headers=get_headers(),
        params=params,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"Zoho API error: HTTP {response.status_code}: "
            f"{response.text}"
        )

    records = response.json().get("data", [])

    print("Historical messages retrieved:", len(records))

    for record in records:
        print("-" * 40)
        print("Zoho Record ID:", record.get("id"))
        print("Message ID:", record.get("Message_ID"))
        print("Group:", record.get("Group_Name"))
        print("Sender:", record.get("Sender_Name"))
        print("WhatsApp ID:", record.get("WhatsApp_ID"))
        print("Date:", record.get("Display_Date"))
        print("Time:", record.get("Display_Time"))
        print("Has message content:", bool(record.get("Message")))

        for field in ("Contact", "Lead", "Deal"):
            lookup = record.get(field)
            record_id = lookup.get("id") if isinstance(lookup, dict) else lookup
            print(f"{field} ID:", record_id)

        whatsapp_id = record.get("WhatsApp_ID")
        if whatsapp_id:
            contact = find_contact_by_whatsapp_id(whatsapp_id)
            lead = find_lead_by_whatsapp_id(whatsapp_id)

            print("Matched Contact ID:", contact.get("id") if contact else None)
            print("Matched Lead ID:", lead.get("id") if lead else None)
if __name__ == "__main__":
    preview_historical_messages()