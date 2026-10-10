# ============================================================
# WhatsApp Incoming Message Schemas
# ============================================================

from typing import Optional, List
from pydantic import BaseModel, Field


# ============================================================
# Group Context
# ============================================================

class GroupContext(BaseModel):
    currentName: Optional[str] = None


# ============================================================
# Message Metadata
# ============================================================

class MessageMeta(BaseModel):
    unixTimestamp: Optional[int] = None
    messageType: Optional[str] = None
    isForwarded: bool = False


# Optional WhatsApp reply relationship
class ThreadContext(BaseModel):
    replyToMessageId: Optional[str] = None


# ============================================================
# Sender Identity
# ============================================================

class SenderIdentity(BaseModel):
    whatsappId: str
    pushName: Optional[str] = None
    currentGroupRole: Optional[str] = None


# ============================================================
# Message Content
# ============================================================

class MessageContent(BaseModel):
    textContent: Optional[str] = None
    hasMediaAttached: bool = False
    hasLinkReferences: bool = False


# ============================================================
# Mentions
# ============================================================

class MentionContext(BaseModel):
    hasExplicitMentions: bool = False
    mentionedUserIds: List[str] = Field(default_factory=list)
    isGroupMentionAll: bool = False


# ============================================================
# Moderation / Pinned Message Information
# ============================================================

class ModerationContext(BaseModel):
    isPinnedMessage: bool = False
    pinnedByAdminId: Optional[str] = None
    isAnnounceMessage: bool = False


# ============================================================
# Incoming WhatsApp Message
# ============================================================

class WhatsAppMessageRequest(BaseModel):

    # Group
    chatId: str
    groupContext: Optional[GroupContext] = None

    # Message
    messageId: str
    messageMeta: Optional[MessageMeta] = None
    threadContext: Optional[ThreadContext] = None

    # Sender
    senderIdentity: SenderIdentity

    # Content
    messageContent: Optional[MessageContent] = None

    # Mention information
    mentionContext: Optional[MentionContext] = None

    # Moderation information
    moderationContext: Optional[ModerationContext] = None

    # Display / media metadata
    displayDate: Optional[str] = Field(
        default=None,
        alias="_displayDate"
    )

    displayTime: Optional[str] = Field(
        default=None,
        alias="_displayTime"
    )

    mediaPath: Optional[str] = Field(
        default=None,
        alias="_mediaPath"
    )

    model_config = {
        "populate_by_name": True,
        "extra": "allow"
    }