from typing import Optional

from app.schemas.message_schema import WhatsAppMessageRequest

from app.repositories.zoho_repository import (
    find_contact_by_whatsapp_id,
    find_lead_by_whatsapp_id,
    create_lead,
    create_contact,
    update_lead,
    update_contact,
    convert_lead_to_contact,
    update_whatsapp_message,
)


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
    """
    Append a new WhatsApp conversation entry without
    overwriting the existing conversation history.
    """

    if not existing_history:
        return new_entry

    return f"{existing_history.rstrip()}\n\n{new_entry}"


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

    updated_history = append_conversation_history(
        existing_history,
        new_entry
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

    updated_history = append_conversation_history(
        existing_history,
        new_entry
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

        contact_result = create_contact(
            contact_record
        )

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

    lead_result = create_lead(
        lead_record
    )

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