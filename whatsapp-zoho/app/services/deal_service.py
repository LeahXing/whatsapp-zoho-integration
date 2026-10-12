import re
from typing import Optional

from app.schemas.message_schema import WhatsAppMessageRequest

from app.repositories.zoho_repository import (
    find_active_deals_by_contact,
    find_whatsapp_messages_by_deal_id,
    find_whatsapp_message_by_message_id,
    create_deal,
    update_deal,
    update_whatsapp_message,
)


# ============================================================
# Conversation History Helpers
# ============================================================

def format_conversation_entry(
    message: WhatsAppMessageRequest
) -> str:
    """
    Format one WhatsApp message for Deal conversation history.

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
        for value in [
            display_date,
            display_time,
        ]
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
        append_conversation_history as sort_history
    )

    return sort_history(existing_history, new_entry)


# ============================================================
# Analyze Commercial Message
# ============================================================

def analyze_commercial_message(
    message: WhatsAppMessageRequest
) -> dict:
    """
    Analyze a WhatsApp message for commercial intent
    and extract basic transaction information.

    Current deterministic logic extracts:

        - commercial intent
        - qualification
        - commodity
        - quantity
        - price

    Commercial intent can be established by:

        1. Explicit commercial / transaction keywords

        OR

        2. Structured transaction information:
           commodity + quantity
           commodity + price

    Later this can be enhanced with an LLM/context layer.
    """

    message_text = (
        message.messageContent.textContent
        if message.messageContent
        else ""
    )

    normalized_text = message_text.strip()

    lower_text = normalized_text.lower()

    # --------------------------------------------------------
    # 1. Commercial / Transaction Keywords
    # --------------------------------------------------------

    commercial_keywords = [

        # Buy / Sell intent
        "buy",
        "buyer",
        "sell",
        "seller",
        "need",
        "require",
        "required",
        "looking for",

        # Pricing / quotation
        "offer",
        "quote",
        "price",
        "available",

        # Transaction context
        "deal",
        "transaction",
        "contract",
        "order",
        "purchase",

        # Deal execution / documents
        "specification",
        "spec",
        "shipment",
        "delivery",
        "invoice",
    ]

    has_commercial_keyword = any(
        re.search(
            r"\b" + re.escape(keyword) + r"\b",
            lower_text,
            re.IGNORECASE,
        )
        for keyword in commercial_keywords
    )

    # --------------------------------------------------------
    # 2. Quantity Extraction
    # --------------------------------------------------------

    quantity = None

    quantity_patterns = [
        r"\b(\d+(?:\.\d+)?)\s*MT\b",
        r"\b(\d+(?:\.\d+)?)\s*tons?\b",
        r"\b(\d+(?:\.\d+)?)\s*tonnes?\b",
        r"\b(\d+(?:\.\d+)?)\s*shares?\b",
    ]

    for pattern in quantity_patterns:

        quantity_match = re.search(
            pattern,
            normalized_text,
            re.IGNORECASE,
        )

        if quantity_match:

            quantity = float(
                quantity_match.group(1)
            )

            break

    # --------------------------------------------------------
    # 3. Price Extraction
    # --------------------------------------------------------

    price = None

    price_patterns = [
        r"\$\s*(\d+(?:\.\d+)?)",
        r"\bUSD\s*(\d+(?:\.\d+)?)\b",
    ]

    for pattern in price_patterns:

        price_match = re.search(
            pattern,
            normalized_text,
            re.IGNORECASE,
        )

        if price_match:

            price = float(
                price_match.group(1)
            )

            break

    # --------------------------------------------------------
    # 4. Commodity Extraction
    # --------------------------------------------------------

    known_commodities = [
        "Urea",
        "Wheat",
        "Rice",
        "Sugar",
        "Corn",
        "Soybean",
    ]

    commodity = None

    for item in known_commodities:

        if re.search(r"\b" + re.escape(item) + r"\b", lower_text, re.IGNORECASE):

            commodity = item

            break

    # Extract explicitly labeled stock symbols.
    stock_match = re.search(
        r"\bStock\s+Symbol\s*:\s*([A-Z]{1,5}(?:\.[A-Z])?)\b",
        normalized_text,
        re.IGNORECASE,
    )
    if stock_match:
        commodity = stock_match.group(1).upper()
    # --------------------------------------------------------
    # 5. Structured Transaction Evidence
    # --------------------------------------------------------
    #
    # Examples:
    #
    #     500 MT Urea
    #
    #     Urea at $385
    #
    #     500 MT Urea at $385
    #
    # These messages contain enough structured transaction
    # information to indicate commercial context even if
    # "buy" or "sell" is not explicitly present.
    # --------------------------------------------------------

    has_transaction_data = (
        commodity is not None
        and (
            quantity is not None
            or price is not None
        )
    )

    # --------------------------------------------------------
    # 6. Final Commercial Intent
    # --------------------------------------------------------

    is_commercial = has_commercial_keyword

    # --------------------------------------------------------
    # 7. Qualification
    # --------------------------------------------------------
    #
    # Current business rule:
    #
    # Commercial intent
    #     +
    # identifiable commodity
    #
    # -> sufficiently qualified for Deal routing
    # --------------------------------------------------------

    is_qualified = (
        is_commercial
        and commodity is not None
    )

    # --------------------------------------------------------
    # 8. Return Analysis
    # --------------------------------------------------------

    # --------------------------------------------------------
    # 8. Classify Message Type
    # --------------------------------------------------------

    message_type = "UNKNOWN"

    news_patterns = [
        r"\bprices?\s+(?:increased|decreased|rose|fell|jumped)\b",
        r"\bmarket\s+(?:news|update|report)\b",
        r"\b(?:profit|revenue|sensex|nifty)\b",
    ]

    enquiry_patterns = [
        r"\b(?:looking to buy|want to buy|need to buy)\b",
        r"\b(?:looking to sell|want to sell)\b",
        r"\b(?:require|looking for)\b",
    ]

    quote_patterns = [
        r"\b(?:we offer|we can offer|our quote|quoted price)\b",
        r"\b(?:can supply|offering)\b",
    ]

    negotiation_patterns = [
        r"\b(?:best price|reduce the price|discount)\b",
        r"\b(?:can you do|counteroffer|counter offer)\b",
    ]

    confirmation_patterns = [
        r"\b(?:deal confirmed|order confirmed)\b",
        r"\b(?:agreed|let's proceed|we accept)\b",
    ]

    def matches(patterns):
        return any(
            re.search(pattern, lower_text, re.IGNORECASE)
            for pattern in patterns
        )

    if matches(news_patterns):
        message_type = "MARKET_NEWS"
    elif matches(confirmation_patterns):
        message_type = "CONFIRMATION"
    elif matches(negotiation_patterns):
        message_type = "NEGOTIATION"
    elif matches(quote_patterns):
        message_type = "QUOTE"
    elif matches(enquiry_patterns):
        message_type = (
            "ENQUIRY" if commodity else "INCOMPLETE_ENQUIRY"
        )

    # --------------------------------------------------------
    # 9. Align commercial flags with message type
    # --------------------------------------------------------

    lifecycle_types = {
        "INCOMPLETE_ENQUIRY",
        "ENQUIRY",
        "QUOTE",
        "NEGOTIATION",
        "CONFIRMATION",
    }

    if message_type == "MARKET_NEWS":
        is_commercial = False
        is_qualified = False
    elif message_type in lifecycle_types:
        is_commercial = True
        is_qualified = commodity is not None

    # --------------------------------------------------------
    # 10. Return Analysis
    # --------------------------------------------------------

    return {
        "is_commercial": is_commercial,
        "is_qualified": is_qualified,
        "commodity": commodity,
        "quantity": quantity,
        "price": price,
        "message_type": message_type,
    }


# ============================================================
# Backward-Compatible Commercial Intent Function
# ============================================================

def detect_commercial_intent(
    message: WhatsAppMessageRequest
) -> dict:
    """
    Backward-compatible wrapper.
    """

    return analyze_commercial_message(
        message
    )


# ============================================================
# Find Matching Existing Deal
# ============================================================

def find_matching_deal(
    active_deals: list,
    commodity: Optional[str],
) -> Optional[dict]:
    """
    Match an existing active Deal by commodity.

    Return a Deal only when exactly one match exists.
    Raise ValueError when multiple Deals match.
    """

    if not commodity:
        return None

    matches = [
        deal
        for deal in active_deals
        if (
            deal.get("Commodity")
            and str(deal["Commodity"]).strip().lower()
            == commodity.strip().lower()
        )
    ]

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        raise ValueError(
            "AMBIGUOUS_DEAL_MATCH: Multiple active Deals "
            f"match commodity '{commodity}'. "
            "Manual Deal selection is required."
        )

    return None



def find_reply_matching_deal(
    message: WhatsAppMessageRequest,
    contact_id: str,
    active_deals: list,
) -> Optional[dict]:
    """
    Resolve a WhatsApp reply to an existing active Deal.

    Never guess when the original message or Deal
    cannot be verified.
    """
    thread = message.threadContext
    reply_id = thread.replyToMessageId if thread else None

    if not reply_id:
        return None

    original = find_whatsapp_message_by_message_id(reply_id)

    if not original:
        raise ValueError(
            "UNRESOLVED_REPLY: Original WhatsApp message not found."
        )

    if str(original.get("Group_ID")) != str(message.chatId):
        raise ValueError(
            "UNRESOLVED_REPLY: Original message belongs to another group."
        )

    deal_lookup = original.get("Deal")
    deal_id = (
        deal_lookup.get("id")
        if isinstance(deal_lookup, dict)
        else None
    )

    if not deal_id:
        raise ValueError(
            "UNRESOLVED_REPLY: Original message has no linked Deal."
        )

    matches = [
        deal for deal in active_deals
        if (
            str(deal.get("id")) == str(deal_id)
            and deal.get("WhatsApp_Active_Deal") is True
            and isinstance(deal.get("Contact_Name"), dict)
            and str(deal["Contact_Name"].get("id")) == str(contact_id)
            and str(deal.get("WhatsApp_Group_ID")) == str(message.chatId)
        )
    ]

    if len(matches) != 1:
        raise ValueError(
            "UNRESOLVED_REPLY: Referenced Deal is not uniquely verified "
            "as active and belonging to this Contact and group."
        )

    return matches[0]


# ============================================================
# Build New Deal Record
# ============================================================

def build_deal_record(
    message: WhatsAppMessageRequest,
    contact_id: str,
    analysis: dict,
) -> dict:
    """
    Build a new Zoho Deal record.
    """

    commodity = analysis.get(
        "commodity"
    )

    quantity = analysis.get(
        "quantity"
    )

    price = analysis.get(
        "price"
    )

    group_name = (
        message.groupContext.currentName
        if message.groupContext
        else None
    )

    conversation_entry = (
        format_conversation_entry(
            message
        )
    )

    # Deal Name must exist in Zoho.

    deal_name_parts = [
        commodity or "WhatsApp Deal",
        message.senderIdentity.pushName
        or message.senderIdentity.whatsappId,
    ]

    deal_name = " - ".join(
        deal_name_parts
    )

    record = {

        "Deal_Name": deal_name,

        "Contact_Name": {
            "id": contact_id
        },

        "Commodity": commodity,
        "Quantity": quantity,
        "Price": price,

        "Stage": "Qualification",

        "WhatsApp_Group_ID": (
            message.chatId
        ),

        "WhatsApp_Group_Name": (
            group_name
        ),

        # Initialize Deal conversation history.

        "WhatsApp_Conversation_History": (
            conversation_entry
        ),

        "WhatsApp_Active_Deal": True,
    }

    return {
        key: value
        for key, value in record.items()
        if value is not None
    }


# ============================================================
# Append History to Existing Deal
# ============================================================

def append_history_to_deal(
    deal: dict,
    message: WhatsAppMessageRequest
) -> None:
    """
    Update one Deal's history in chronological order when safe.
    Preserve existing history if structured records are incomplete.
    """

    deal_id = deal["id"]
    existing_history = (
        deal.get("WhatsApp_Conversation_History") or ""
    )
    new_entry = format_conversation_entry(message)

    from app.services.conversation_history import (
        append_conversation_history as safe_append,
        format_sorted_message_history,
    )

    fallback = safe_append(existing_history, new_entry)

    try:
        records = find_whatsapp_messages_by_deal_id(deal_id)

        # The current message is linked to the Deal after this
        # history update, so include it explicitly for sorting.
        current_record = {
            "Message_ID": message.messageId,
            "Unix_Timestamp": (
                message.messageMeta.unixTimestamp
                if message.messageMeta else 0
            ),
            "Sender_Name": message.senderIdentity.pushName,
            "WhatsApp_ID": message.senderIdentity.whatsappId,
            "Display_Date": message.displayDate,
            "Display_Time": message.displayTime,
            "Message": (
                message.messageContent.textContent
                if message.messageContent else ""
            ),
        }

        current_id = str(current_record["Message_ID"])
        records = [
            r for r in records
            if str(r.get("Message_ID") or "") != current_id
        ]
        records.append(current_record)

        formatted = format_sorted_message_history(records)

        if existing_history and existing_history not in formatted:
            updated_history = fallback
        elif new_entry not in formatted:
            updated_history = fallback
        else:
            updated_history = formatted
    except Exception:
        updated_history = fallback

    update_deal(
        deal_id,
        {
            "WhatsApp_Conversation_History": updated_history,
            "WhatsApp_Group_ID": message.chatId,
            "WhatsApp_Group_Name": (
                message.groupContext.currentName
                if message.groupContext
                else None
            ),
        }
    )


# ============================================================
# Process Deal Routing
# ============================================================

def process_deal(
    message: WhatsAppMessageRequest,
    whatsapp_message_record_id: str,
    contact_id: Optional[str],
    analysis: Optional[dict] = None,
) -> dict:
    """
    Determine whether the incoming WhatsApp message should
    be associated with a Deal.

    Business rules:

        - Deal requires a Contact.
        - Message must represent a qualified commercial enquiry.
        - Existing active Deal is matched by commodity.
        - Matching Deal receives appended conversation history.
        - Otherwise a new Deal is created.
    """

    # --------------------------------------------------------
    # 1. Deal requires Contact
    # --------------------------------------------------------

    if not contact_id:

        return {
            "deal_action": "NO_DEAL",
            "reason": (
                "Sender is not a Contact."
            ),
            "deal_id": None,
        }

    # --------------------------------------------------------
    # 2. Use existing analysis when provided
    # --------------------------------------------------------

    if analysis is None:

        analysis = (
            analyze_commercial_message(
                message
            )
        )

    # --------------------------------------------------------
    # 3. No commercial intent
    # --------------------------------------------------------

    # Prioritize explicit WhatsApp replies.
    thread = message.threadContext
    reply_id = thread.replyToMessageId if thread else None

    if reply_id:
        active_deals = find_active_deals_by_contact(contact_id)

        try:
            matching_deal = find_reply_matching_deal(
                message,
                contact_id,
                active_deals,
            )
        except ValueError as exc:
            return {
                "deal_action": "MANUAL_REVIEW",
                "reason": str(exc),
                "deal_id": None,
                "analysis": analysis,
            }

        if matching_deal:
            deal_id = matching_deal["id"]

            append_history_to_deal(matching_deal, message)

            update_whatsapp_message(
                whatsapp_message_record_id,
                {"Deal": {"id": deal_id}},
            )

            return {
                "deal_action": "LINK_EXISTING",
                "deal_id": deal_id,
                "match_method": "WHATSAPP_REPLY",
                "analysis": analysis,
            }

    if not analysis.get(
        "is_commercial"
    ):

        return {
            "deal_action": "NO_DEAL",
            "reason": (
                "No commercial intent detected."
            ),
            "deal_id": None,
            "analysis": analysis,
        }

    # --------------------------------------------------------
    # 4. Commercial but not qualified
    # --------------------------------------------------------

    if not analysis.get(
        "is_qualified"
    ):

        return {
            "deal_action": "NO_DEAL",
            "reason": (
                "Commercial intent detected, "
                "but message is not sufficiently "
                "qualified for Deal routing."
            ),
            "deal_id": None,
            "analysis": analysis,
        }

    # --------------------------------------------------------
    # 5. Get Active Deals for Contact
    # --------------------------------------------------------

    active_deals = (
        find_active_deals_by_contact(
            contact_id
        )
    )

    # --------------------------------------------------------
    # 6. Try to Match Existing Deal
    # --------------------------------------------------------

    try:
        matching_deal = find_matching_deal(
            active_deals,
            analysis.get("commodity"),
        )
    except ValueError as exc:
        if "AMBIGUOUS_DEAL_MATCH" not in str(exc):
            raise

        return {
            "deal_action": "MANUAL_REVIEW",
            "reason": str(exc),
            "deal_id": None,
            "analysis": analysis,
        }

    if matching_deal:

        deal_id = matching_deal["id"]

        # Append message to transaction-specific
        # Deal conversation history.

        append_history_to_deal(
            matching_deal,
            message
        )

        # Link WhatsApp Message -> existing Deal.

        update_whatsapp_message(
            whatsapp_message_record_id,
            {
                "Deal": {
                    "id": deal_id
                }
            }
        )

        return {
            "deal_action": (
                "LINK_EXISTING"
            ),
            "deal_id": deal_id,
            "analysis": analysis,
        }

    # --------------------------------------------------------
    # 7. Prevent new Deals from follow-up messages
    # --------------------------------------------------------

    message_type = analysis.get("message_type")

    if message_type in {"NEGOTIATION", "CONFIRMATION"}:
        return {
            "deal_action": "MANUAL_REVIEW",
            "reason": (
                f"{message_type} message has no matching active Deal. "
                "Manual Deal selection is required."
            ),
            "deal_id": None,
            "analysis": analysis,
        }

    # --------------------------------------------------------
    # 8. Create New Deal
    # --------------------------------------------------------

    deal_data = build_deal_record(
        message,
        contact_id,
        analysis,
    )

    created_deal = create_deal(
        deal_data
    )

    deal_id = (
        created_deal
        .get("details", {})
        .get("id")
    )

    if not deal_id:

        raise RuntimeError(
            "Zoho created the Deal but "
            "did not return a Deal ID: "
            f"{created_deal}"
        )

    # --------------------------------------------------------
    # 8. Link WhatsApp Message -> New Deal
    # --------------------------------------------------------

    update_whatsapp_message(
        whatsapp_message_record_id,
        {
            "Deal": {
                "id": deal_id
            }
        }
    )

    return {
        "deal_action": "CREATE_NEW",
        "deal_id": deal_id,
        "analysis": analysis,
    }
