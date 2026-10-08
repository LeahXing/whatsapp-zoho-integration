import re
from typing import Optional

from app.schemas.message_schema import WhatsAppMessageRequest

from app.repositories.zoho_repository import (
    find_active_deals_by_contact,
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
    """
    Append a new WhatsApp message to existing Deal history.
    """

    if not existing_history:
        return new_entry

    return f"{existing_history.rstrip()}\n\n{new_entry}"


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
        keyword in lower_text
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

        if item.lower() in lower_text:

            commodity = item

            break

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

    is_commercial = (
        has_commercial_keyword
        or has_transaction_data
    )

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

    return {
        "is_commercial": is_commercial,
        "is_qualified": is_qualified,
        "commodity": commodity,
        "quantity": quantity,
        "price": price,
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
    Attempt to match the incoming message to an existing
    active Deal.

    Current rule:

        Match by Commodity.

    Later this can use:

        commodity
        quantity
        price
        recent conversation
        semantic/LLM analysis
    """

    if not commodity:
        return None

    for deal in active_deals:

        deal_commodity = deal.get(
            "Commodity"
        )

        if (
            deal_commodity
            and deal_commodity.lower()
            == commodity.lower()
        ):

            return deal

    return None


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
    Append the incoming WhatsApp message to the existing
    Deal conversation history without overwriting it.
    """

    deal_id = deal["id"]

    existing_history = (
        deal.get(
            "WhatsApp_Conversation_History"
        )
        or ""
    )

    new_entry = format_conversation_entry(
        message
    )

    updated_history = (
        append_conversation_history(
            existing_history,
            new_entry
        )
    )

    update_deal(
        deal_id,
        {
            "WhatsApp_Conversation_History": (
                updated_history
            ),
            "WhatsApp_Group_ID": (
                message.chatId
            ),
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

    matching_deal = (
        find_matching_deal(
            active_deals,
            analysis.get(
                "commodity"
            ),
        )
    )

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
    # 7. Create New Deal
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