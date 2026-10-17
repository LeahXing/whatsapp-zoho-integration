from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DUBAI_TIMEZONE = ZoneInfo("Asia/Dubai")


def format_dubai_timestamp(unix_timestamp: float) -> str:
    """Convert a WhatsApp Unix timestamp into Dubai local time."""
    dt = datetime.fromtimestamp(
        float(unix_timestamp),
        tz=timezone.utc,
    ).astimezone(DUBAI_TIMEZONE)

    return dt.strftime("%Y-%m-%d %H:%M:%S GST (Dubai)")