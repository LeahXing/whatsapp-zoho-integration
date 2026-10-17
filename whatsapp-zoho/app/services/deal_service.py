import re
from datetime import datetime, timezone
from typing import Optional

from app.schemas.message_schema import WhatsAppMessageRequest

from app.repositories.zoho_repository import (
    find_active_deals_by_contact,
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
        # Weight
        r"\b(\d+(?:\.\d+)?)\s*(?:MT|metric\s+tons?)\b",
        r"\b(\d+(?:\.\d+)?)\s*(?:tons?|tonnes?)\b",
        r"\b(\d+(?:\.\d+)?)\s*(?:kilograms?|kgs?)\b",
        r"\b(\d+(?:\.\d+)?)\s*(?:grams?|g)\b",
        r"\b(\d+(?:\.\d+)?)\s*(?:ounces?|oz)\b",
        r"\b(\d+(?:\.\d+)?)\s*(?:pounds?|lbs?)\b",

        # Stocks
        r"\b(\d+(?:\.\d+)?)\s*(?:shares?|stocks?)\b",

        # Volume
        r"\b(\d+(?:\.\d+)?)\s*(?:barrels?|bbl)\b",
        r"\b(\d+(?:\.\d+)?)\s*(?:liters?|litres?)\b",

        # Other
        r"\b(\d+(?:\.\d+)?)\s*(?:units?|lots?)\b",
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
        # Precious metals
        "Gold", "Silver", "Platinum", "Palladium",

        # Industrial metals
        "Copper", "Aluminum", "Aluminium",
        "Iron", "Iron Ore", "Steel", "Zinc",
        "Nickel", "Tin", "Lithium", "Cobalt",

        # Energy
        "Crude Oil", "Brent Crude", "WTI",
        "Natural Gas", "LNG", "Coal",
        "Diesel", "Gasoline",

        # Agriculture
        "Wheat", "Rice", "Corn", "Maize",
        "Soybean", "Soybeans", "Sugar",
        "Cotton", "Coffee", "Cocoa",
        "Palm Oil", "Sunflower Oil",

        # Fertilizers
        "Urea", "DAP", "MAP", "NPK",
        "Potash", "Ammonium Nitrate",

        # US stock names
        "Apple", "Microsoft", "NVIDIA",
        "Tesla", "Amazon", "Google",
        "Alphabet", "Netflix", "Intel",
        "Salesforce",

        # US stock tickers
        "AAPL", "MSFT", "NVDA", "TSLA",
        "AMZN", "GOOGL", "GOOG", "NFLX",
        "INTC", "CRM", "AMD", "CSCO",
        "ORCL", "JPM", "BAC",
    ]

    commodity_aliases = {
        "aluminium": "Aluminum",
        "maize": "Corn",
        "soybeans": "Soybean",
        "brent crude": "Crude Oil",

        "apple": "AAPL",
        "microsoft": "MSFT",
        "nvidia": "NVDA",
        "tesla": "TSLA",
        "amazon": "AMZN",
        "google": "GOOGL",
        "alphabet": "GOOGL",
        "netflix": "NFLX",
        "intel": "INTC",
        "salesforce": "CRM",
    }

    commodity = None

    for item in sorted(known_commodities, key=len, reverse=True):
        if re.search(
            r"\b" + re.escape(item) + r"\b",
            normalized_text,
            re.IGNORECASE,
        ):
            commodity = commodity_aliases.get(
                item.lower(),
                item,
            )
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
# Manual Deal routing: conversation windows, not commodity intent
# ============================================================

CLOSED_STAGES = {"closed won", "closed lost"}


def _utc_datetime(value):
    """Parse Zoho Date/Time or WhatsApp Unix time into aware UTC datetime.

    Unix seconds and milliseconds are supported. Naive Date/Time values are
    rejected: they must carry an explicit offset to prevent wrong matches.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) or (
        isinstance(value, str) and value.strip().replace(".", "", 1).isdigit()
    ):
        number = float(value)
        if number > 1e11:  # milliseconds
            number /= 1000
        return datetime.fromtimestamp(number, tz=timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        raise ValueError(f"Unsupported timestamp type: {type(value).__name__}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Date/Time must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def _lookup_id(value):
    return str(value.get("id")) if isinstance(value, dict) and value.get("id") else None


def _is_closed(deal):
    return str(deal.get("Stage") or "").strip().lower() in CLOSED_STAGES


def _within_window(message_time, deal):
    start = _utc_datetime(deal.get("WhatsApp_Conversation_Start"))
    end = _utc_datetime(deal.get("WhatsApp_Conversation_End"))
    if start is None:
        return False  # explicit start is mandatory
    if end is not None and end < start:
        raise ValueError("Deal conversation End precedes Start")
    return start <= message_time and (end is None or message_time <= end)


def find_matching_deal(active_deals, contact_id, group_id, message_time):
    """Return the unique open Deal in the message's inclusive time window.

    A candidate must match Contact, group, active flag, and open Stage.
    Ambiguous or malformed windows are not silently accepted.
    """
    matches = []
    for deal in active_deals:
        if _lookup_id(deal.get("Contact_Name")) != str(contact_id):
            continue
        if str(deal.get("WhatsApp_Group_ID") or "") != str(group_id):
            continue
        if deal.get("WhatsApp_Active_Deal") is not True or _is_closed(deal):
            continue
        try:
            in_window = _within_window(message_time, deal)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"INVALID_DEAL_WINDOW for Deal {deal.get('id')}: {exc}") from exc
        if in_window:
            matches.append(deal)
    if len(matches) > 1:
        raise ValueError(
            "AMBIGUOUS_DEAL_MATCH: Multiple open Deals match Contact, "
            "WhatsApp group and message timestamp. Resolve overlapping windows in Zoho."
        )
    return matches[0] if matches else None


def process_deal(
    message: WhatsAppMessageRequest,
    whatsapp_message_record_id: str,
    contact_id: Optional[str],
    analysis: Optional[dict] = None,
) -> dict:
    """Link a message to an existing manually created Deal; never create one.

    A message's original WhatsApp timestamp controls inclusion. Closed Deals
    are excluded from live routing, even for delayed messages; a separate
    historical backfill service will handle closed-Deal windows.
    """
    if analysis is None:
        analysis = analyze_commercial_message(message)
    if not contact_id:
        return {
            "deal_action": "NO_DEAL", "reason": "Sender is not a Contact.",
            "deal_id": None, "analysis": analysis,
        }
    try:
        meta = message.messageMeta
        raw_time = meta.unixTimestamp if meta else None
        if raw_time is None:
            raise ValueError("Original WhatsApp Unix timestamp is missing")
        message_time = _utc_datetime(raw_time)
        if message_time is None:
            raise ValueError("Original WhatsApp Unix timestamp is missing")
        active_deals = find_active_deals_by_contact(contact_id)
        matching = find_matching_deal(
            active_deals, contact_id, message.chatId, message_time
        )
    except (ValueError, TypeError, OverflowError) as exc:
        return {
            "deal_action": "MANUAL_REVIEW", "reason": str(exc),
            "deal_id": None, "analysis": analysis,
        }

    if matching is None:
        return {
            "deal_action": "NO_DEAL",
            "reason": "No eligible manually created open Deal matches Contact, group and conversation window.",
            "deal_id": None, "analysis": analysis,
        }

    deal_id = matching["id"]
    update_whatsapp_message(
        whatsapp_message_record_id, {"Deal": {"id": deal_id}}
    )
    return {
        "deal_action": "LINK_EXISTING", "deal_id": deal_id,
        "match_method": "CONTACT_GROUP_TIME_WINDOW", "analysis": analysis,
    }
