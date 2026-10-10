"""
Database Mapper Module.
Transforms raw conversational entities into JSON payloads matching target schemas.
"""

from typing import Dict, Any
import hashlib

class WhatsAppDatabaseMapper:
    @staticmethod
    def build_schema_record(
        group_name: str, 
        msg_id: str, 
        sender: str, 
        clean_body: str, 
        media_type: str, 
        unix_ts: int, 
        date_str: str, 
        time_str_ampm: str, 
        file_path: str
    ) -> Dict[str, Any]:
        """Maps data items to structured payload constraints (WhatsAppGroupChatMessageLog Specifications)."""
        return {
            "chatId": f"{int(hashlib.sha256(group_name.encode()).hexdigest(), 16) % 10**10}@g.us",
            "groupContext": {
                "currentName": group_name, 
                "activeMemberCount": 0
            },
            "messageId": msg_id,
            "messageMeta": {
                "unixTimestamp": unix_ts,
                "messageType": media_type,
                "isForwarded": False,
                "forwardingScore": 0
            },
            "senderIdentity": {
                "whatsappId": (
                    f"{hashlib.sha256(sender.strip().encode('utf-8')).hexdigest()[:20]}@c.us"
                    if sender and sender.strip()
                    else "unknown@c.us"
                ),
                "pushName": sender or "Unknown",
                "currentGroupRole": "member"
            },
            "messageContent": {
                "textContent": clean_body,
                "hasMediaAttached": media_type != "chat",
                "hasLinkReferences": "http://" in clean_body or "https://" in clean_body
            },
            "moderationState": {
                "isPinnedMessage": False, 
                "pinnedByAdminId": None, 
                "isAnnounceMessage": False
            },
            "groupMentions": {
                "hasExplicitMentions": "@" in clean_body,
                "mentionedUserIds": [],
                "isGroupMentionAll": "@all" in clean_body.lower()
            },
            "threadContext": None,
            "deliveryReceipts": [],
            "_displayDate": date_str,
            "_displayTime": time_str_ampm,
            "_mediaPath": file_path
        }
