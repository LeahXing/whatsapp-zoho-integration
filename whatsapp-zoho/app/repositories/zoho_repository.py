import os
import time

import requests
from dotenv import load_dotenv


# ============================================================
# Load Environment Variables
# ============================================================

load_dotenv()

ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")

ZOHO_ACCOUNTS_URL = os.getenv(
    "ZOHO_ACCOUNTS_URL",
    "https://accounts.zoho.in"
)

ZOHO_API_DOMAIN = os.getenv(
    "ZOHO_API_DOMAIN",
    "https://www.zohoapis.in"
)


# ============================================================
# Zoho CRM Module Configuration
# ============================================================

WHATSAPP_MESSAGES_MODULE = "WhatsApp_Messages"
LEADS_MODULE = "Leads"
CONTACTS_MODULE = "Contacts"
DEALS_MODULE = "Deals"


# ============================================================
# Zoho Access Token Cache
# ============================================================

_ZOHO_ACCESS_TOKEN = None
_ZOHO_ACCESS_TOKEN_EXPIRES_AT = 0

# Refresh the token slightly before its actual expiration time.
_TOKEN_EXPIRY_BUFFER_SECONDS = 60


# ============================================================
# Get Zoho Access Token
# ============================================================

def get_access_token():
    """
    Return a valid Zoho OAuth access token.

    The access token is cached in memory and reused until
    shortly before it expires.

    A new access token is requested from Zoho only when:
        1. No cached token exists, or
        2. The cached token is close to expiration.
    """

    global _ZOHO_ACCESS_TOKEN
    global _ZOHO_ACCESS_TOKEN_EXPIRES_AT

    current_time = time.time()

    # --------------------------------------------------------
    # Reuse cached access token
    # --------------------------------------------------------

    if (
        _ZOHO_ACCESS_TOKEN
        and current_time < _ZOHO_ACCESS_TOKEN_EXPIRES_AT
    ):
        return _ZOHO_ACCESS_TOKEN

    # --------------------------------------------------------
    # Request a new access token
    # --------------------------------------------------------

    url = f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token"

    params = {
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "refresh_token": ZOHO_REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }

    response = requests.post(
        url,
        params=params,
        timeout=30
    )

    if not response.ok:
        try:
            error_detail = response.json()
        except ValueError:
            error_detail = response.text

        raise RuntimeError(
            f"Zoho authentication failed. "
            f"HTTP {response.status_code}: {error_detail}"
        )

    data = response.json()

    access_token = data.get("access_token")

    if not access_token:
        raise RuntimeError(
            f"Zoho did not return an access token: {data}"
        )

    # Zoho normally returns expires_in.
    # Use 3600 seconds as a fallback.
    try:
        expires_in = int(
            data.get("expires_in", 3600)
        )
    except (TypeError, ValueError):
        expires_in = 3600

    # --------------------------------------------------------
    # Cache access token
    # --------------------------------------------------------

    _ZOHO_ACCESS_TOKEN = access_token

    _ZOHO_ACCESS_TOKEN_EXPIRES_AT = (
        current_time
        + expires_in
        - _TOKEN_EXPIRY_BUFFER_SECONDS
    )

    return _ZOHO_ACCESS_TOKEN


# ============================================================
# Generate Zoho Request Headers
# ============================================================

def get_headers():
    """
    Generate headers required for Zoho CRM API requests.

    get_access_token() reuses the cached access token
    while it remains valid.
    """

    access_token = get_access_token()

    return {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "Content-Type": "application/json"
    }


# ============================================================
# Check Whether WhatsApp Message Already Exists
# ============================================================

def find_whatsapp_message_by_message_id(
    message_id: str
):
    """
    Search WhatsApp_Messages using Message_ID.

    Returns:
        Zoho record dictionary if found.
        None if no matching record exists.
    """

    url = (
        f"{ZOHO_API_DOMAIN}/crm/v8/"
        f"{WHATSAPP_MESSAGES_MODULE}/search"
    )

    params = {
        "criteria": (
            f"(Message_ID:equals:{message_id})"
        )
    }

    response = requests.get(
        url,
        headers=get_headers(),
        params=params,
        timeout=30
    )

    # Zoho returns 204 when no matching record exists.
    if response.status_code == 204:
        return None

    if not response.ok:
        try:
            error_detail = response.json()
        except ValueError:
            error_detail = response.text

        raise RuntimeError(
            f"Zoho WhatsApp message search failed. "
            f"HTTP {response.status_code}: {error_detail}"
        )

    result = response.json()

    records = result.get("data", [])

    if not records:
        return None

    return records[0]

# ============================================================
# Find Historical WhatsApp Messages by Sender Name
# ============================================================

def find_whatsapp_messages_by_sender_name(
    sender_name: str
) -> list:
    """
    Retrieve historical WhatsApp messages by sender name.

    Read-only operation.
    Supports pagination.
    """

    url = (
        f"{ZOHO_API_DOMAIN}/crm/v8/"
        f"{WHATSAPP_MESSAGES_MODULE}/search"
    )

    all_records = []
    page = 1

    while True:

        params = {
            "criteria": f"(Sender_Name:equals:{sender_name})",
            "page": page,
            "per_page": 200,
        }

        response = requests.get(
            url,
            headers=get_headers(),
            params=params,
            timeout=30
        )

        if response.status_code == 204:
            break

        if not response.ok:
            raise RuntimeError(
                f"Historical message search failed: "
                f"HTTP {response.status_code}: "
                f"{response.text}"
            )

        result = response.json()

        all_records.extend(result.get("data", []))

        if not result.get("info", {}).get("more_records", False):
            break

        page += 1

    return sorted(
        all_records,
        key=lambda record: int(
            record.get("Unix_Timestamp") or 0
        )
    )

# ============================================================
# Create WhatsApp Message Record
# ============================================================

def create_whatsapp_message(
    record_data: dict
):
    """
    Create one record in the Zoho WhatsApp_Messages module.

    record_data must use Zoho field API names.
    """

    url = (
        f"{ZOHO_API_DOMAIN}/crm/v8/"
        f"{WHATSAPP_MESSAGES_MODULE}"
    )

    payload = {
        "data": [
            record_data
        ]
    }

    response = requests.post(
        url,
        headers=get_headers(),
        json=payload,
        timeout=30
    )

    if not response.ok:
        try:
            error_detail = response.json()
        except ValueError:
            error_detail = response.text

        raise RuntimeError(
            f"Zoho create WhatsApp message failed. "
            f"HTTP {response.status_code}: {error_detail}"
        )

    result = response.json()

    records = result.get("data", [])

    if not records:
        raise RuntimeError(
            f"Zoho returned no record data: {result}"
        )

    record_result = records[0]

    if record_result.get("status") != "success":
        raise RuntimeError(
            f"Zoho failed to create WhatsApp message: "
            f"{record_result}"
        )

    return record_result


# ============================================================
# Generic Zoho Record Search
# ============================================================

def search_zoho_records(
    module_name: str,
    criteria: str
):
    """
    Search records in a Zoho CRM module.

    Returns:
        List of matching Zoho records.
        Empty list if no records are found.
    """

    url = (
        f"{ZOHO_API_DOMAIN}/crm/v8/"
        f"{module_name}/search"
    )

    params = {
        "criteria": criteria
    }

    response = requests.get(
        url,
        headers=get_headers(),
        params=params,
        timeout=30
    )

    if response.status_code == 204:
        return []

    if not response.ok:
        try:
            error_detail = response.json()
        except ValueError:
            error_detail = response.text

        raise RuntimeError(
            f"Zoho search failed for module "
            f"{module_name}. "
            f"HTTP {response.status_code}: "
            f"{error_detail}"
        )

    result = response.json()

    return result.get("data", [])


# ============================================================
# Generic Zoho Record Creation
# ============================================================

def create_zoho_record(
    module_name: str,
    record_data: dict
):
    """
    Create one record in a Zoho CRM module.

    Returns the first Zoho record result.

    Example success response shape:

        {
            "status": "success",
            "details": {
                "id": "..."
            }
        }

    Therefore callers creating records should read the ID using:

        result["details"]["id"]
    """

    url = (
        f"{ZOHO_API_DOMAIN}/crm/v8/"
        f"{module_name}"
    )

    payload = {
        "data": [
            record_data
        ]
    }

    response = requests.post(
        url,
        headers=get_headers(),
        json=payload,
        timeout=30
    )

    if not response.ok:
        try:
            error_detail = response.json()
        except ValueError:
            error_detail = response.text

        raise RuntimeError(
            f"Zoho create failed for module "
            f"{module_name}. "
            f"HTTP {response.status_code}: "
            f"{error_detail}"
        )

    result = response.json()

    records = result.get("data", [])

    if not records:
        raise RuntimeError(
            f"Zoho returned no record data "
            f"for module {module_name}: {result}"
        )

    record_result = records[0]

    if record_result.get("status") != "success":
        raise RuntimeError(
            f"Zoho failed to create record in "
            f"{module_name}: {record_result}"
        )

    return record_result


# ============================================================
# Generic Zoho Record Update
# ============================================================

def update_zoho_record(
    module_name: str,
    record_id: str,
    record_data: dict
):
    """
    Update one existing Zoho CRM record.
    """

    url = (
        f"{ZOHO_API_DOMAIN}/crm/v8/"
        f"{module_name}/{record_id}"
    )

    payload = {
        "data": [
            record_data
        ]
    }

    response = requests.put(
        url,
        headers=get_headers(),
        json=payload,
        timeout=30
    )

    if not response.ok:
        try:
            error_detail = response.json()
        except ValueError:
            error_detail = response.text

        raise RuntimeError(
            f"Zoho update failed for module "
            f"{module_name}, record {record_id}. "
            f"HTTP {response.status_code}: "
            f"{error_detail}"
        )

    result = response.json()

    records = result.get("data", [])

    if not records:
        raise RuntimeError(
            f"Zoho returned no update data "
            f"for module {module_name}: {result}"
        )

    record_result = records[0]

    if record_result.get("status") != "success":
        raise RuntimeError(
            f"Zoho failed to update record in "
            f"{module_name}: {record_result}"
        )

    return record_result

# ============================================================
# Upload Attachment to Zoho CRM Record
# ============================================================

def upload_attachment(
    module_name: str,
    record_id: str,
    file_path: str
):
    """
    Upload a local file as an attachment to a Zoho CRM record.

    Supported modules include:
        Leads
        Contacts
        Deals

    Examples:

        upload_attachment(
            LEADS_MODULE,
            lead_id,
            file_path
        )

        upload_attachment(
            CONTACTS_MODULE,
            contact_id,
            file_path
        )

        upload_attachment(
            DEALS_MODULE,
            deal_id,
            file_path
        )
    """

    # --------------------------------------------------------
    # Validate arguments
    # --------------------------------------------------------

    if not module_name:
        raise ValueError(
            "module_name is required."
        )

    if not record_id:
        raise ValueError(
            "record_id is required."
        )

    if not file_path:
        raise ValueError(
            "file_path is required."
        )

    # --------------------------------------------------------
    # Verify local file exists
    # --------------------------------------------------------

    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"Media file not found: {file_path}"
        )

    # --------------------------------------------------------
    # Build Zoho Attachments API URL
    # --------------------------------------------------------

    url = (
        f"{ZOHO_API_DOMAIN}/crm/v8/"
        f"{module_name}/{record_id}/Attachments"
    )

    # --------------------------------------------------------
    # Prepare headers
    # --------------------------------------------------------

    headers = get_headers().copy()

    # File uploads use multipart/form-data.
    #
    # Do NOT manually set Content-Type.
    # requests will automatically generate:
    #
    # multipart/form-data; boundary=...
    #
    # when the files= parameter is used.

    headers.pop(
        "Content-Type",
        None
    )

    # --------------------------------------------------------
    # Get file name
    # --------------------------------------------------------

    file_name = os.path.basename(
        file_path
    )

    # --------------------------------------------------------
    # Upload file
    # --------------------------------------------------------

    try:

        with open(
            file_path,
            "rb"
        ) as file_object:

            files = {
                "file": (
                    file_name,
                    file_object
                )
            }

            response = requests.post(
                url,
                headers=headers,
                files=files,
                timeout=60
            )

    except OSError as exc:

        raise RuntimeError(
            f"Unable to read media file: "
            f"{file_path}"
        ) from exc

    # --------------------------------------------------------
    # Handle Zoho API error
    # --------------------------------------------------------

    if not response.ok:

        try:
            error_detail = (
                response.json()
            )

        except ValueError:
            error_detail = (
                response.text
            )

        raise RuntimeError(
            f"Zoho attachment upload failed "
            f"for module {module_name}, "
            f"record {record_id}. "
            f"HTTP {response.status_code}: "
            f"{error_detail}"
        )

    # --------------------------------------------------------
    # Parse Zoho response
    # --------------------------------------------------------

    try:
        result = response.json()

    except ValueError as exc:

        raise RuntimeError(
            "Zoho attachment upload returned "
            "an invalid JSON response."
        ) from exc

    records = result.get(
        "data",
        []
    )

    if not records:

        raise RuntimeError(
            f"Zoho returned no attachment data "
            f"for module {module_name}, "
            f"record {record_id}: "
            f"{result}"
        )

    attachment_result = (
        records[0]
    )

    # --------------------------------------------------------
    # Verify Zoho success
    # --------------------------------------------------------

    if (
        attachment_result.get("status")
        != "success"
    ):

        raise RuntimeError(
            f"Zoho failed to upload "
            f"attachment to "
            f"{module_name}: "
            f"{attachment_result}"
        )

    # --------------------------------------------------------
    # Return Zoho attachment result
    # --------------------------------------------------------

    return attachment_result

# ============================================================
# Contact Operations
# ============================================================

def find_contact_by_whatsapp_id(
    whatsapp_id: str
):
    """
    Find a Contact using WhatsApp_ID.

    Contact lookup has higher routing priority than Lead lookup.
    """

    records = search_zoho_records(
        CONTACTS_MODULE,
        f"(WhatsApp_ID:equals:{whatsapp_id})"
    )

    if not records:
        return None

    return records[0]


def create_contact(
    record_data: dict
):
    """
    Create a new Contact.

    Zoho requires Last_Name for Contacts.
    record_data must therefore contain Last_Name.
    """

    return create_zoho_record(
        CONTACTS_MODULE,
        record_data
    )


def update_contact(
    contact_id: str,
    record_data: dict
):
    """
    Update an existing Contact.
    """

    return update_zoho_record(
        CONTACTS_MODULE,
        contact_id,
        record_data
    )


# ============================================================
# Lead Operations
# ============================================================

def find_lead_by_whatsapp_id(
    whatsapp_id: str
):
    """
    Find a Lead using WhatsApp_ID.
    """

    records = search_zoho_records(
        LEADS_MODULE,
        f"(WhatsApp_ID:equals:{whatsapp_id})"
    )

    if not records:
        return None

    return records[0]


def create_lead(
    record_data: dict
):
    """
    Create a new Lead.
    """

    return create_zoho_record(
        LEADS_MODULE,
        record_data
    )


def update_lead(
    lead_id: str,
    record_data: dict
):
    """
    Update an existing Lead.
    """

    return update_zoho_record(
        LEADS_MODULE,
        lead_id,
        record_data
    )


# ============================================================
# Convert Lead to Contact
# ============================================================

def convert_lead_to_contact(
    lead_id: str,
    overwrite: bool = True,
    notify_lead_owner: bool = False,
    notify_new_entity_owner: bool = False
):
    """
    Convert a qualified Zoho Lead into a Contact.

    This function intentionally does NOT create a Deal.
    Deal creation/matching remains the responsibility of
    deal_service.py after the Contact has been resolved.

    If the Lead has no Company value and no Account is supplied,
    Zoho can convert the Lead into a Contact without creating
    an Account.

    Returns:
        {
            "contact_id": "...",
            "contact_name": "...",
            "account_id": None or "...",
            "account_name": None or "...",
            "raw": {...}
        }
    """

    url = (
        f"{ZOHO_API_DOMAIN}/crm/v8/"
        f"{LEADS_MODULE}/{lead_id}/actions/convert"
    )

    conversion_data = {
        "overwrite": overwrite,
        "notify_lead_owner": notify_lead_owner,
        "notify_new_entity_owner": notify_new_entity_owner
    }

    payload = {
        "data": [
            conversion_data
        ]
    }

    response = requests.post(
        url,
        headers=get_headers(),
        json=payload,
        timeout=30
    )

    if not response.ok:
        try:
            error_detail = response.json()
        except ValueError:
            error_detail = response.text

        raise RuntimeError(
            f"Zoho Lead conversion failed for "
            f"Lead {lead_id}. "
            f"HTTP {response.status_code}: "
            f"{error_detail}"
        )

    result = response.json()

    records = result.get("data", [])

    if not records:
        raise RuntimeError(
            f"Zoho returned no Lead conversion data "
            f"for Lead {lead_id}: {result}"
        )

    conversion_result = records[0]

    if conversion_result.get("status") != "success":
        raise RuntimeError(
            f"Zoho failed to convert Lead "
            f"{lead_id}: {conversion_result}"
        )

    details = conversion_result.get("details", {})

    contact = details.get("Contacts")
    account = details.get("Accounts")

    if not contact or not contact.get("id"):
        raise RuntimeError(
            f"Zoho converted Lead {lead_id}, "
            f"but no Contact ID was returned: "
            f"{conversion_result}"
        )

    return {
        "contact_id": contact.get("id"),
        "contact_name": contact.get("name"),
        "account_id": (
            account.get("id")
            if account
            else None
        ),
        "account_name": (
            account.get("name")
            if account
            else None
        ),
        "raw": conversion_result
    }


# ============================================================
# Deal Operations
# ============================================================

def find_active_deals_by_contact(
    contact_id: str
):
    """
    Find active Deals belonging to a Contact.

    More than one active Deal may exist for the
    same Contact.
    """

    criteria = (
        f"((Contact_Name:equals:{contact_id})"
        f"and(WhatsApp_Active_Deal:equals:true))"
    )

    return search_zoho_records(
        DEALS_MODULE,
        criteria
    )


def create_deal(
    record_data: dict
):
    """
    Create a new Deal.
    """

    return create_zoho_record(
        DEALS_MODULE,
        record_data
    )


def update_deal(
    deal_id: str,
    record_data: dict
):
    """
    Update an existing Deal.
    """

    return update_zoho_record(
        DEALS_MODULE,
        deal_id,
        record_data
    )


# ============================================================
# WhatsApp Message Update
# ============================================================

def update_whatsapp_message(
    message_record_id: str,
    record_data: dict
):
    """
    Update an existing WhatsApp_Messages record.

    Used to attach Lead, Contact and Deal lookups
    after the original WhatsApp message has already been stored.
    """

    return update_zoho_record(
        WHATSAPP_MESSAGES_MODULE,
        message_record_id,
        record_data
    )