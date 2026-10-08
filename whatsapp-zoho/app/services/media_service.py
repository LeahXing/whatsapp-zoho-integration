# ============================================================
# WhatsApp Media Service
# ============================================================

import os
from typing import Optional

from app.schemas.message_schema import WhatsAppMessageRequest

from app.repositories.zoho_repository import (
    upload_attachment,
)


# ============================================================
# Supported Media Types
# ============================================================

SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
}

SUPPORTED_DOCUMENT_EXTENSIONS = {
    ".pdf",
}

SUPPORTED_MEDIA_EXTENSIONS = (
    SUPPORTED_IMAGE_EXTENSIONS
    | SUPPORTED_DOCUMENT_EXTENSIONS
)


# ============================================================
# Check Whether Message Has Media
# ============================================================

def has_media(
    message: WhatsAppMessageRequest
) -> bool:
    """
    Determine whether the incoming WhatsApp message
    contains a media attachment.
    """

    if not message.messageContent:
        return False

    return bool(
        message.messageContent.hasMediaAttached
    )


# ============================================================
# Get Media Path
# ============================================================

def get_media_path(
    message: WhatsAppMessageRequest
) -> Optional[str]:
    """
    Return the media path supplied by the WhatsApp
    source platform.

    Example:

        /Users/hayley/Documents/test.pdf

    Returns None when no media path is available.
    """

    media_path = message.mediaPath

    if not media_path:
        return None

    return media_path.strip()


# ============================================================
# Get File Extension
# ============================================================

def get_file_extension(
    file_path: str
) -> str:
    """
    Extract and normalize the file extension.

    Example:

        wheat_specification.PDF

    becomes:

        .pdf
    """

    _, extension = os.path.splitext(
        file_path
    )

    return extension.lower()


# ============================================================
# Detect Media Type
# ============================================================

def detect_media_type(
    file_path: str
) -> str:
    """
    Determine the media category.

    Returns:

        image
        pdf
        unsupported
    """

    extension = get_file_extension(
        file_path
    )

    if extension in SUPPORTED_IMAGE_EXTENSIONS:
        return "image"

    if extension in SUPPORTED_DOCUMENT_EXTENSIONS:
        return "pdf"

    return "unsupported"


# ============================================================
# Validate Media
# ============================================================

def validate_media(
    file_path: str
) -> dict:
    """
    Validate the media before attempting upload.
    """

    extension = get_file_extension(
        file_path
    )

    media_type = detect_media_type(
        file_path
    )

    is_supported = (
        extension
        in SUPPORTED_MEDIA_EXTENSIONS
    )

    file_exists = os.path.isfile(
        file_path
    )

    return {
        "is_supported": is_supported,
        "file_exists": file_exists,
        "media_type": media_type,
        "extension": extension,
        "file_path": file_path,
    }


# ============================================================
# Determine Attachment Targets
# ============================================================

def determine_attachment_targets(
    whatsapp_message_record_id: Optional[str],
    person_type: Optional[str],
    person_id: Optional[str],
    deal_id: Optional[str] = None,
) -> list[dict]:
    """
    Determine which Zoho CRM records should receive
    the media attachment.

    Business rules:

    WhatsApp Message:
        Always attach the media to the corresponding
        WhatsApp_Messages record when its record ID exists.

    Lead:
        Attach to WhatsApp_Messages and Lead.

    Contact without Deal:
        Attach to WhatsApp_Messages and Contact.

    Contact with Deal:
        Attach to WhatsApp_Messages, Contact, and Deal.
    """

    targets = []

    # --------------------------------------------------------
    # WhatsApp Message
    # --------------------------------------------------------
    #
    # Every incoming media file belongs to the original
    # WhatsApp message. Therefore the WhatsApp_Messages
    # record should always receive the attachment when
    # its Zoho record ID is available.
    # --------------------------------------------------------

    if whatsapp_message_record_id:

        targets.append(
            {
                "module": "WhatsApp_Messages",
                "record_id": (
                    whatsapp_message_record_id
                ),
            }
        )

    # --------------------------------------------------------
    # Lead
    # --------------------------------------------------------

    if (
        person_type == "lead"
        and person_id
    ):

        targets.append(
            {
                "module": "Leads",
                "record_id": person_id,
            }
        )

    # --------------------------------------------------------
    # Contact
    # --------------------------------------------------------

    elif (
        person_type == "contact"
        and person_id
    ):

        targets.append(
            {
                "module": "Contacts",
                "record_id": person_id,
            }
        )

    # --------------------------------------------------------
    # Deal
    # --------------------------------------------------------

    if deal_id:

        targets.append(
            {
                "module": "Deals",
                "record_id": deal_id,
            }
        )

    return targets


# ============================================================
# Prepare Media Processing
# ============================================================

def prepare_media_processing(
    message: WhatsAppMessageRequest,
    whatsapp_message_record_id: Optional[str],
    person_type: Optional[str],
    person_id: Optional[str],
    deal_id: Optional[str] = None,
) -> dict:
    """
    Validate the media and determine which Zoho
    records should receive the attachment.

    This function does NOT upload the file.
    """

    # --------------------------------------------------------
    # 1. Check for media
    # --------------------------------------------------------

    if not has_media(message):

        return {
            "has_media": False,
            "media_action": "NO_MEDIA",
            "file_path": None,
            "media_type": None,
            "targets": [],
        }

    # --------------------------------------------------------
    # 2. Get media path
    # --------------------------------------------------------

    file_path = get_media_path(
        message
    )

    if not file_path:

        return {
            "has_media": True,
            "media_action": "MEDIA_PATH_MISSING",
            "file_path": None,
            "media_type": None,
            "targets": [],
        }

    # --------------------------------------------------------
    # 3. Validate media
    # --------------------------------------------------------

    validation = validate_media(
        file_path
    )

    if not validation["is_supported"]:

        return {
            "has_media": True,
            "media_action": "UNSUPPORTED_MEDIA",
            "file_path": file_path,
            "media_type": (
                validation["media_type"]
            ),
            "extension": (
                validation["extension"]
            ),
            "targets": [],
        }

    if not validation["file_exists"]:

        return {
            "has_media": True,
            "media_action": "FILE_NOT_FOUND",
            "file_path": file_path,
            "media_type": (
                validation["media_type"]
            ),
            "extension": (
                validation["extension"]
            ),
            "targets": [],
        }

    # --------------------------------------------------------
    # 4. Determine Zoho targets
    # --------------------------------------------------------

    targets = determine_attachment_targets(
        whatsapp_message_record_id=(
            whatsapp_message_record_id
        ),
        person_type=person_type,
        person_id=person_id,
        deal_id=deal_id,
    )

    if not targets:

        return {
            "has_media": True,
            "media_action": "NO_ATTACHMENT_TARGET",
            "file_path": file_path,
            "media_type": (
                validation["media_type"]
            ),
            "extension": (
                validation["extension"]
            ),
            "targets": [],
        }

    # --------------------------------------------------------
    # 5. Ready for upload
    # --------------------------------------------------------

    return {
        "has_media": True,
        "media_action": "READY_FOR_UPLOAD",
        "file_path": file_path,
        "media_type": (
            validation["media_type"]
        ),
        "extension": (
            validation["extension"]
        ),
        "targets": targets,
    }


# ============================================================
# Upload Media to Zoho
# ============================================================

def upload_media_to_zoho(
    message: WhatsAppMessageRequest,
    whatsapp_message_record_id: Optional[str],
    person_type: Optional[str],
    person_id: Optional[str],
    deal_id: Optional[str] = None,
) -> dict:
    """
    Process and upload a WhatsApp media attachment
    to the appropriate Zoho CRM records.

    Examples:

    Lead:

        file -> WhatsApp_Messages
             -> Lead

    Contact:

        file -> WhatsApp_Messages
             -> Contact

    Contact + Deal:

        file -> WhatsApp_Messages
             -> Contact
             -> Deal
    """

    # --------------------------------------------------------
    # 1. Prepare media
    # --------------------------------------------------------

    media_info = prepare_media_processing(
        message=message,
        whatsapp_message_record_id=(
            whatsapp_message_record_id
        ),
        person_type=person_type,
        person_id=person_id,
        deal_id=deal_id,
    )

    # --------------------------------------------------------
    # 2. Stop if media is not ready
    # --------------------------------------------------------

    if (
        media_info["media_action"]
        != "READY_FOR_UPLOAD"
    ):

        return media_info

    # --------------------------------------------------------
    # 3. Upload to each target
    # --------------------------------------------------------

    upload_results = []

    for target in media_info["targets"]:

        module_name = target["module"]

        record_id = target["record_id"]

        try:

            result = upload_attachment(
                module_name=module_name,
                record_id=record_id,
                file_path=(
                    media_info["file_path"]
                ),
            )

            upload_results.append(
                {
                    "module": module_name,
                    "record_id": record_id,
                    "status": "SUCCESS",
                    "result": result,
                }
            )

        except Exception as exc:

            upload_results.append(
                {
                    "module": module_name,
                    "record_id": record_id,
                    "status": "FAILED",
                    "error": str(exc),
                }
            )

    # --------------------------------------------------------
    # 4. Determine Overall Upload Status
    # --------------------------------------------------------

    successful_uploads = [
        result
        for result in upload_results
        if result["status"] == "SUCCESS"
    ]

    failed_uploads = [
        result
        for result in upload_results
        if result["status"] == "FAILED"
    ]

    if (
        successful_uploads
        and not failed_uploads
    ):

        media_action = "UPLOAD_SUCCESS"

    elif (
        successful_uploads
        and failed_uploads
    ):

        media_action = "PARTIAL_UPLOAD"

    else:

        media_action = "UPLOAD_FAILED"

    # --------------------------------------------------------
    # 5. Return Result
    # --------------------------------------------------------

    return {
        "has_media": True,
        "media_action": media_action,
        "file_path": (
            media_info["file_path"]
        ),
        "media_type": (
            media_info["media_type"]
        ),
        "extension": (
            media_info["extension"]
        ),
        "targets": (
            media_info["targets"]
        ),
        "uploads": upload_results,
    }