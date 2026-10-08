# ============================================================
# WhatsApp Message Service
# ============================================================

from app.schemas.message_schema import WhatsAppMessageRequest

from app.repositories.zoho_repository import (
    find_whatsapp_message_by_message_id,
    create_whatsapp_message,
)

from app.services.routing_service import (
    route_whatsapp_sender,
)

from app.services.deal_service import (
    analyze_commercial_message,
    process_deal,
)

from app.services.media_service import (
    upload_media_to_zoho,
)


# ============================================================
# Build Zoho WhatsApp_Messages Record
# ============================================================

def build_zoho_message_record(
    message: WhatsAppMessageRequest
) -> dict:
    """
    Convert the incoming WhatsApp message into
    Zoho WhatsApp_Messages field API names.
    """

    record = {

        # ----------------------------------------------------
        # Zoho mandatory record name
        # ----------------------------------------------------

        "Name": message.messageId,

        # ----------------------------------------------------
        # Message Identification
        # ----------------------------------------------------

        "Message_ID": message.messageId,
        "Group_ID": message.chatId,

        # ----------------------------------------------------
        # Group Information
        # ----------------------------------------------------

        "Group_Name": (
            message.groupContext.currentName
            if message.groupContext
            else None
        ),

        # ----------------------------------------------------
        # Sender Information
        # ----------------------------------------------------

        "WhatsApp_ID": (
            message.senderIdentity.whatsappId
        ),

        "Sender_Name": (
            message.senderIdentity.pushName
        ),

        "Group_Role": (
            message.senderIdentity.currentGroupRole
        ),

        # ----------------------------------------------------
        # Message Metadata
        # ----------------------------------------------------

        "Unix_Timestamp": (
            message.messageMeta.unixTimestamp
            if message.messageMeta
            else None
        ),

        "Message_Type": (
            message.messageMeta.messageType
            if message.messageMeta
            else None
        ),

        "Is_Forwarded": (
            message.messageMeta.isForwarded
            if message.messageMeta
            else False
        ),

        # ----------------------------------------------------
        # Message Content
        # ----------------------------------------------------

        "Message": (
            message.messageContent.textContent
            if message.messageContent
            else None
        ),

        "Has_Media_Attached": (
            message.messageContent.hasMediaAttached
            if message.messageContent
            else False
        ),

        "Has_Link_References": (
            message.messageContent.hasLinkReferences
            if message.messageContent
            else False
        ),

        # ----------------------------------------------------
        # Mention Information
        # ----------------------------------------------------

        "Has_Explicit_Mentions": (
            message.mentionContext.hasExplicitMentions
            if message.mentionContext
            else False
        ),

        "Mentioned_User_IDs": (
            ",".join(
                message.mentionContext.mentionedUserIds
            )
            if (
                message.mentionContext
                and message.mentionContext.mentionedUserIds
            )
            else None
        ),

        "Is_Group_Mention_All": (
            message.mentionContext.isGroupMentionAll
            if message.mentionContext
            else False
        ),

        # ----------------------------------------------------
        # Moderation Information
        # ----------------------------------------------------

        "Is_Pinned_Message": (
            message.moderationContext.isPinnedMessage
            if message.moderationContext
            else False
        ),

        "Pinned_By_Admin_ID": (
            message.moderationContext.pinnedByAdminId
            if message.moderationContext
            else None
        ),

        "Is_Announce_Message": (
            message.moderationContext.isAnnounceMessage
            if message.moderationContext
            else False
        ),

        # ----------------------------------------------------
        # Display / Media Metadata
        # ----------------------------------------------------

        "Display_Date": message.displayDate,
        "Display_Time": message.displayTime,
        "Media_Path": message.mediaPath,
    }

    # Remove None values.
    # Keep False and 0 because they are valid values.

    return {
        key: value
        for key, value in record.items()
        if value is not None
    }


# ============================================================
# Process Incoming WhatsApp Message
# ============================================================

def process_whatsapp_message(
    message: WhatsAppMessageRequest
) -> dict:
    """
    Main orchestration workflow.

    Order:

        1. Check duplicate Message_ID.
        2. Store WhatsApp message FIRST.
        3. Analyze commercial intent and qualification.
        4. Route sender to Contact / Lead.
        5. Process Deal using the same analysis.
        6. Process media attachments.
        7. Return complete processing result.

    Important:

        The WhatsApp message is always stored before CRM
        routing, Deal processing, or media processing.
    """

    # --------------------------------------------------------
    # 1. Duplicate Check
    # --------------------------------------------------------

    existing_message = (
        find_whatsapp_message_by_message_id(
            message.messageId
        )
    )

    if existing_message:

        return {
            "status": "duplicate",
            "message": (
                "Message already exists in Zoho CRM."
            ),
            "message_id": message.messageId,
            "zoho_message_record_id": (
                existing_message.get("id")
            ),
        }

    # --------------------------------------------------------
    # 2. Build WhatsApp_Messages Record
    # --------------------------------------------------------

    zoho_message_data = (
        build_zoho_message_record(
            message
        )
    )

    # --------------------------------------------------------
    # 3. Store WhatsApp Message FIRST
    # --------------------------------------------------------

    try:
        created_message = create_whatsapp_message(
            zoho_message_data
        )

    except RuntimeError as exc:
        error_text = str(exc)

        if (
            "DUPLICATE_DATA" in error_text
            and "'api_name': 'Message_ID'" in error_text
        ):
            existing_message = find_whatsapp_message_by_message_id(
                message.messageId
            )

            if existing_message:
                return {
                    "status": "duplicate",
                    "message": "Message already exists in Zoho CRM.",
                    "message_id": message.messageId,
                    "zoho_message_record_id": existing_message.get("id"),
                }

        raise

    whatsapp_message_record_id = (
        created_message
        .get("details", {})
        .get("id")
    )

    if not whatsapp_message_record_id:

        raise RuntimeError(
            "Zoho created the WhatsApp message but "
            "did not return a record ID."
        )

    # --------------------------------------------------------
    # 4. Analyze Message BEFORE Person Routing
    # --------------------------------------------------------
    #
    # Qualification determines:
    #
    # Existing Lead + unqualified
    #     -> remain Lead
    #
    # Existing Lead + qualified
    #     -> convert Lead -> Contact
    #
    # New sender + unqualified
    #     -> create Lead
    #
    # New sender + qualified
    #     -> create Contact
    # --------------------------------------------------------

    analysis = analyze_commercial_message(
        message
    )

    # --------------------------------------------------------
    # 5. Route Sender
    # --------------------------------------------------------

    routing_result = route_whatsapp_sender(
        message=message,
        whatsapp_message_record_id=(
            whatsapp_message_record_id
        ),
        analysis=analysis,
    )

    person_type = routing_result.get(
        "person_type"
    )

    person_id = routing_result.get(
        "person_id"
    )

    # --------------------------------------------------------
    # 6. Deal Processing
    # --------------------------------------------------------
    #
    # A Deal can only belong to a Contact.
    #
    # The same analysis generated above is passed into
    # process_deal(). We therefore do not classify/extract
    # the message twice.
    # --------------------------------------------------------

    if person_type == "contact":

        deal_result = process_deal(
            message=message,
            whatsapp_message_record_id=(
                whatsapp_message_record_id
            ),
            contact_id=person_id,
            analysis=analysis,
        )

    else:

        deal_result = {
            "deal_action": "NO_DEAL",
            "reason": (
                "Sender is currently a Lead."
            ),
            "deal_id": None,
            "analysis": analysis,
        }

    # --------------------------------------------------------
    # 7. Media Processing
    # --------------------------------------------------------
    #
    # Media processing happens AFTER person routing and
    # Deal processing.
    #
    # At this point we know:
    #
    #     person_type
    #     person_id
    #     deal_id
    #
    # Attachment rules:
    #
    # Lead:
    #     -> Lead attachment
    #
    # Contact without Deal:
    #     -> Contact attachment
    #
    # Contact with Deal:
    #     -> Contact attachment
    #     -> Deal attachment
    # --------------------------------------------------------

    deal_id = deal_result.get(
        "deal_id"
    )

    media_result = upload_media_to_zoho(
        message=message,
        whatsapp_message_record_id=(
            whatsapp_message_record_id
        ),
        person_type=person_type,
        person_id=person_id,
        deal_id=deal_id,
    )

    # --------------------------------------------------------
    # 8. Return Complete Processing Result
    # --------------------------------------------------------

    return {
        "status": "created",

        "message_id": message.messageId,

        "zoho_message_record_id": (
            whatsapp_message_record_id
        ),

        "analysis": analysis,

        "routing": {
            "person_type": person_type,
            "person_id": person_id,

            "action": routing_result.get(
                "action"
            ),

            "created": routing_result.get(
                "created",
                False
            ),

            "converted": routing_result.get(
                "converted",
                False
            ),

            "source_lead_id": (
                routing_result.get(
                    "source_lead_id"
                )
            ),
        },

        "deal": deal_result,

        "media": media_result,
    }