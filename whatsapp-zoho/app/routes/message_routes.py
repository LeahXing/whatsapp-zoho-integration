# ============================================================
# WhatsApp Message API Routes
# ============================================================

from fastapi import APIRouter, HTTPException

from app.schemas.message_schema import WhatsAppMessageRequest
from app.services.message_service import process_whatsapp_message


# ============================================================
# Router Configuration
# ============================================================

router = APIRouter(
    prefix="/api/v1/messages",
    tags=["WhatsApp Messages"]
)


# ============================================================
# Receive WhatsApp Message
# ============================================================

@router.post("/")
def receive_whatsapp_message(
    message: WhatsAppMessageRequest
):
    """
    Receive one WhatsApp message and store it in Zoho CRM.

    Workflow:
        1. Validate incoming JSON payload.
        2. Safely extract nested data (Sender, Group, Text, Media).
        3. Store/Process message in Zoho CRM.
        4. Return response.
    """

    try:
        # Convert incoming Pydantic object to dict
        data = message.model_dump() if hasattr(message, "model_dump") else message.dict()

        # Safely extract flat OR nested payload fields
        msg_id = data.get("messageId")
        group_name = data.get("groupName") or data.get("groupContext", {}).get("currentName")
        sender = data.get("sender") or data.get("senderIdentity", {}).get("pushName")
        display_date = data.get("displayDate")
        display_time = data.get("displayTime")
        text_content = data.get("messageText") or data.get("messageContent", {}).get("textContent")
        media_path = data.get("mediaPath") or data.get("_mediaPath")

        print("\n============================================================")
        print("📥 RECEIVED INCOMING WHATSAPP MESSAGE PAYLOAD")
        print("============================================================")
        print(f"Message ID  : {msg_id}")
        print(f"Group Name  : {group_name}")
        print(f"Sender      : {sender}")
        print(f"Date / Time : {display_date} {display_time}")
        print(f"Text Content: {text_content}")
        print(f"Media Path  : {media_path if media_path else 'None'}")
        print("------------------------------------------------------------")
        print("Raw Payload Dictionary:")
        print(data)
        print("============================================================\n")

        # Process record into Zoho CRM
        result = process_whatsapp_message(message)

        return result

    except Exception as exc:
        print(f"❌ Error processing message {msg_id if 'msg_id' in locals() else ''}: {exc}")
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )