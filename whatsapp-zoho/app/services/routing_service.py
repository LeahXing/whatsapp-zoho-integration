import threading
from typing import Optional

from app.schemas.message_schema import WhatsAppMessageRequest

from app.repositories.zoho_repository import (
    ZohoDuplicateError,
    find_contact_by_whatsapp_id,
    find_lead_by_whatsapp_id,
    find_whatsapp_messages_by_whatsapp_id,
    create_lead,
    create_contact,
    update_lead,
    update_contact,
    convert_lead_to_contact,
    update_whatsapp_message,
)


# One lock per WhatsApp sender (within this Python process).
_sender_locks = {}
_sender_locks_guard = threading.Lock()


def get_sender_lock(whatsapp_id: str):
    with _sender_locks_guard:
        if whatsapp_id not in _sender_locks:
            _sender_locks[whatsapp_id] = threading.Lock()
        return _sender_locks[whatsapp_id]


# =========================================================
# Conversation History Helpers
# =========================================================

def format_conversation_entry(
    message: WhatsAppMessageRequest
) -> str:
    """
    Format one WhatsApp message for CRM conversation history.

    Format:
        Sender Name | displayDate displayTime
        Message text
    """

    sender_name = (
        message.senderIdentity.pushName
        or message.senderIdentity.whatsappId
        or "Unknown Sender"
    )

    message_text = (
        message.messageContent.textContent
        if message.messageContent
        else ""
    )

    display_date = message.displayDate or ""
    display_time = message.displayTime or ""

    # Timestamp = displayDate + displayTime
    timestamp = " ".join(
        value
        for value in [display_date, display_time]
        if value
    )

    if timestamp:
        header = f"{sender_name} | {timestamp}"
    else:
        header = sender_name

    return f"{header}\n{message_text}"


def append_conversation_history(
    existing_history: Optional[str],
    new_entry: str
) -> str:
    from app.services.conversation_history import (
        append_conversation_history as safe_append
    )
    return safe_append(existing_history, new_entry)


def build_safe_chronological_history(
    existing_history: str,
    message: WhatsAppMessageRequest
) -> str:
    from app.services.conversation_history import (
        format_sorted_message_history
    )

    new_entry = format_conversation_entry(message)
    fallback = append_conversation_history(existing_history, new_entry)

    try:
        records = find_whatsapp_messages_by_whatsapp_id(
            message.senderIdentity.whatsappId
        )
        formatted = format_sorted_message_history(records)

        # Never discard historical text absent from structured records.
        if existing_history and existing_history not in formatted:
            return fallback

        # Never omit the incoming message.
        if new_entry not in formatted:
            return fallback

        return formatted
    except Exception:
        return fallback


# =========================================================
# Build Lead
# =========================================================

def build_lead_record(
    message: WhatsAppMessageRequest
) -> dict:

    sender_name = (
        message.senderIdentity.pushName
        or message.senderIdentity.whatsappId
        or "Unknown WhatsApp User"
    )

    conversation_entry = format_conversation_entry(message)

    return {
        "Last_Name": sender_name,
        "WhatsApp_ID": message.senderIdentity.whatsappId,
        "WhatsApp_Group_ID": message.chatId,
        "WhatsApp_Group_Name": message.groupContext.currentName,
        "Lead_Source": "WhatsApp",
        "WhatsApp_Conversation_History": conversation_entry,
    }


# =========================================================
# Build Contact
# =========================================================

def build_contact_record(
    message: WhatsAppMessageRequest
) -> dict:

    sender_name = (
        message.senderIdentity.pushName
        or message.senderIdentity.whatsappId
        or "Unknown WhatsApp User"
    )

    conversation_entry = format_conversation_entry(message)

    return {
        "Last_Name": sender_name,
        "WhatsApp_ID": message.senderIdentity.whatsappId,
        "WhatsApp_Group_ID": message.chatId,
        "WhatsApp_Group_Name": message.groupContext.currentName,
        "WhatsApp_Conversation_History": conversation_entry,
    }


# =========================================================
# Append History to Existing Lead
# =========================================================

def append_history_to_lead(
    lead: dict,
    message: WhatsAppMessageRequest
) -> str:
    """
    Append a new WhatsApp conversation entry without
    overwriting the existing Lead conversation history.

    Returns:
        Complete updated conversation history.

    The returned history is important when a qualified
    Lead is converted into a Contact. Zoho does not
    automatically transfer our custom WhatsApp conversation
    history field during Lead conversion, so routing_service
    explicitly copies this complete history to the Contact.
    """

    lead_id = lead["id"]

    existing_history = (
        lead.get("WhatsApp_Conversation_History")
        or ""
    )

    new_entry = format_conversation_entry(message)

    updated_history = build_safe_chronological_history(
        existing_history,
        message
    )

    update_lead(
        lead_id,
        {
            "WhatsApp_Conversation_History": updated_history,
            "WhatsApp_Group_ID": message.chatId,
            "WhatsApp_Group_Name": message.groupContext.currentName,
        }
    )

    return updated_history


# =========================================================
# Append History to Existing Contact
# =========================================================

def append_history_to_contact(
    contact: dict,
    message: WhatsAppMessageRequest
) -> None:

    contact_id = contact["id"]

    existing_history = (
        contact.get("WhatsApp_Conversation_History")
        or ""
    )

    new_entry = format_conversation_entry(message)

    updated_history = build_safe_chronological_history(
        existing_history,
        message
    )

    update_contact(
        contact_id,
        {
            "WhatsApp_Conversation_History": updated_history,
            "WhatsApp_Group_ID": message.chatId,
            "WhatsApp_Group_Name": message.groupContext.currentName,
        }
    )


# =========================================================
# Route WhatsApp Sender
# =========================================================

def route_whatsapp_sender(
    message: WhatsAppMessageRequest,
    whatsapp_message_record_id: str,
    analysis: dict
) -> dict:
    whatsapp_id = message.senderIdentity.whatsappId

    with get_sender_lock(whatsapp_id):
        return _route_whatsapp_sender_locked(
            message,
            whatsapp_message_record_id,
            analysis
        )


def _route_whatsapp_sender_locked(
    message: WhatsAppMessageRequest,
    whatsapp_message_record_id: str,
    analysis: dict
) -> dict:

    whatsapp_id = message.senderIdentity.whatsappId

    is_qualified = analysis.get(
        "is_qualified",
        False
    )

    # -----------------------------------------------------
    # 1. CONTACT has highest priority
    # -----------------------------------------------------

    contact = find_contact_by_whatsapp_id(
        whatsapp_id
    )

    if contact:

        contact_id = contact["id"]

        # Append new WhatsApp message to complete
        # Contact conversation history.
        append_history_to_contact(
            contact,
            message
        )

        update_whatsapp_message(
            whatsapp_message_record_id,
            {
                "Contact": contact_id
            }
        )

        return {
            "person_type": "contact",
            "person_id": contact_id,
            "action": "CONTACT_FOUND",
            "created": False,
            "converted": False,
            "source_lead_id": None,
        }

    # -----------------------------------------------------
    # 2. No Contact -> look for existing Lead
    # -----------------------------------------------------

    lead = find_lead_by_whatsapp_id(
        whatsapp_id
    )

    if lead:

        lead_id = lead["id"]

        # -------------------------------------------------
        # Existing Lead becomes qualified
        # -------------------------------------------------

        if is_qualified:

            # -------------------------------------------------
            # STEP 1:
            # Append the qualifying message to the Lead.
            #
            # IMPORTANT:
            # Keep the returned complete history because Zoho
            # does not automatically copy this custom field
            # during Lead -> Contact conversion.
            # -------------------------------------------------

            updated_history = append_history_to_lead(
                lead,
                message
            )

            # -------------------------------------------------
            # STEP 2:
            # Perform the real Zoho Lead -> Contact conversion.
            # -------------------------------------------------

            conversion_result = (
                convert_lead_to_contact(
                    lead_id
                )
            )

            contact_id = (
                conversion_result["contact_id"]
            )

            # -------------------------------------------------
            # STEP 3:
            # Explicitly initialize the converted Contact.
            #
            # This preserves:
            #   - WhatsApp ID
            #   - Current WhatsApp Group ID
            #   - Current WhatsApp Group Name
            #   - COMPLETE conversation history accumulated
            #     while the person was still a Lead
            #
            # Example:
            #
            # Greeting 1
            # Greeting 2
            # Transaction enquiry
            #
            # all become Contact conversation history.
            # -------------------------------------------------

            update_contact(
                contact_id,
                {
                    "WhatsApp_ID": whatsapp_id,
                    "WhatsApp_Group_ID": message.chatId,
                    "WhatsApp_Group_Name": (
                        message.groupContext.currentName
                    ),
                    "WhatsApp_Conversation_History": (
                        updated_history
                    ),
                }
            )

            # -------------------------------------------------
            # STEP 4:
            # Link the stored WhatsApp message to the newly
            # converted Contact.
            # -------------------------------------------------

            update_whatsapp_message(
                whatsapp_message_record_id,
                {
                    "Contact": contact_id
                }
            )

            return {
                "person_type": "contact",
                "person_id": contact_id,
                "action": "LEAD_CONVERTED",
                "created": False,
                "converted": True,
                "source_lead_id": lead_id,
            }

        # -------------------------------------------------
        # Existing Lead remains unqualified
        # -------------------------------------------------

        append_history_to_lead(
            lead,
            message
        )

        update_whatsapp_message(
            whatsapp_message_record_id,
            {
                "Lead": lead_id
            }
        )

        return {
            "person_type": "lead",
            "person_id": lead_id,
            "action": "LEAD_FOUND",
            "created": False,
            "converted": False,
            "source_lead_id": None,
        }

    # -----------------------------------------------------
    # 3. No Contact and No Lead
    # -----------------------------------------------------

    # -----------------------------------------------------
    # Qualified sender -> create Contact directly
    # -----------------------------------------------------

    if is_qualified:

        contact_record = build_contact_record(
            message
        )

        try:
            contact_result = create_contact(
                contact_record
            )
        except ZohoDuplicateError:
            existing_contact = find_contact_by_whatsapp_id(
                whatsapp_id
            )

            if existing_contact is None:
                raise RuntimeError(
                    "Zoho reported a duplicate Contact, "
                    "but the existing Contact could not be found."
                )

            append_history_to_contact(
                existing_contact,
                message
            )

            contact_id = existing_contact["id"]

            update_whatsapp_message(
                whatsapp_message_record_id,
                {"Contact": contact_id}
            )

            return {
                "person_type": "contact",
                "person_id": contact_id,
                "action": "CONTACT_DUPLICATE_RECOVERED",
                "created": False,
                "converted": False,
                "source_lead_id": None,
            }

        # Zoho create response:
        #
        # {
        #     "status": "success",
        #     "details": {
        #         "id": "..."
        #     }
        # }

        contact_id = contact_result["details"]["id"]

        update_whatsapp_message(
            whatsapp_message_record_id,
            {
                "Contact": contact_id
            }
        )

        return {
            "person_type": "contact",
            "person_id": contact_id,
            "action": "CONTACT_CREATED",
            "created": True,
            "converted": False,
            "source_lead_id": None,
        }

    # -----------------------------------------------------
    # New unqualified sender -> create Lead
    # -----------------------------------------------------

    lead_record = build_lead_record(
        message
    )

    try:
        lead_result = create_lead(
            lead_record
        )
    except ZohoDuplicateError:
        existing_lead = find_lead_by_whatsapp_id(
            whatsapp_id
        )

        if existing_lead is None:
            raise RuntimeError(
                "Zoho reported a duplicate Lead, "
                "but the existing Lead could not be found."
            )

        append_history_to_lead(
            existing_lead,
            message
        )

        lead_id = existing_lead["id"]

        update_whatsapp_message(
            whatsapp_message_record_id,
            {"Lead": lead_id}
        )

        return {
            "person_type": "lead",
            "person_id": lead_id,
            "action": "LEAD_DUPLICATE_RECOVERED",
            "created": False,
            "converted": False,
            "source_lead_id": None,
        }

    # Zoho create response:
    #
    # {
    #     "status": "success",
    #     "details": {
    #         "id": "..."
    #     }
    # }

    lead_id = lead_result["details"]["id"]

    update_whatsapp_message(
        whatsapp_message_record_id,
        {
            "Lead": lead_id
        }
    )

    return {
        "person_type": "lead",
        "person_id": lead_id,
        "action": "LEAD_CREATED",
        "created": True,
        "converted": False,
        "source_lead_id": None,
    }
