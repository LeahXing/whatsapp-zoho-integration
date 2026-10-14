import requests

from app.repositories.zoho_repository import (
    ZOHO_API_DOMAIN,
    WHATSAPP_MESSAGES_MODULE,
    get_headers,
)


def preview_historical_messages():
    url = (
        f"{ZOHO_API_DOMAIN}/crm/v8/"
        f"{WHATSAPP_MESSAGES_MODULE}"
    )

    params = {
        "fields": (
            "Message_ID,Group_Name,Sender_Name,"
            "Display_Date,Display_Time,Message"
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
        print("Date:", record.get("Display_Date"))
        print("Time:", record.get("Display_Time"))
        print("Has message content:", bool(record.get("Message")))


if __name__ == "__main__":
    preview_historical_messages()