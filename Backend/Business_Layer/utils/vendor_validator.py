# Backend/Business_Layer/utils/vendor_validator.py
import re

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# 4th character of a PAN encodes the holder's entity type (Income Tax Dept spec).
PAN_ENTITY_TYPE_CODES = set("PCHFATBLJG")

# Placeholder PANs seen in test/demo data — not a real allocation.
DUMMY_PAN_BLACKLIST = {"AAAAA9999A", "ABCDE1234F", "ZZZZZ9999Z"}

VENDOR_NAME_MIN_LENGTH = 2
VENDOR_NAME_MAX_LENGTH = 200
VENDOR_NAME_CHAR_REGEX = re.compile(r"^[A-Za-z0-9&.,'\-()/ ]+$")

EMAIL_MAX_LENGTH = 150
DISPOSABLE_EMAIL_DOMAINS = {
    "mailinator.com",
    "guerrillamail.com",
    "10minutemail.com",
    "tempmail.com",
    "yopmail.com",
    "trashmail.com",
    "throwawaymail.com",
    "getnada.com",
    "fakeinbox.com",
    "dispostable.com",
}

PHONE_MIN_DIGITS = 7
PHONE_MAX_DIGITS = 15

IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

BANK_ACCOUNT_HOLDER_MIN_LENGTH = 2
BANK_ACCOUNT_HOLDER_MAX_LENGTH = 150
BANK_ACCOUNT_NUMBER_MIN_LENGTH = 6
BANK_ACCOUNT_NUMBER_MAX_LENGTH = 20


def validate_vendor_name(vendor_name: str, strict: bool = True) -> str:
    """
    Validates a vendor's display name. `strict=False` (GST_VERIFIED vendors,
    where the name comes from the GST registry) only enforces the base
    required-non-empty rule; the format rules below are skipped since the
    name is already authoritative.
    """
    if not isinstance(vendor_name, str):
        raise ValueError("vendor_name must be a string")

    normalized = vendor_name.strip()

    if not normalized:
        raise ValueError("vendor_name is required")

    if not strict:
        return normalized

    if len(normalized) < VENDOR_NAME_MIN_LENGTH:
        raise ValueError(
            f"vendor_name must be at least {VENDOR_NAME_MIN_LENGTH} characters"
        )

    if len(normalized) > VENDOR_NAME_MAX_LENGTH:
        raise ValueError(
            f"vendor_name must not exceed {VENDOR_NAME_MAX_LENGTH} characters"
        )

    if not VENDOR_NAME_CHAR_REGEX.match(normalized):
        raise ValueError(
            "vendor_name contains invalid characters: only letters, digits, "
            "spaces, and & . , ' - ( ) / are allowed"
        )

    if normalized.replace(" ", "").isdigit():
        raise ValueError("vendor_name cannot be numeric only")

    return normalized


def validate_pan(pan_number: str, strict: bool = True) -> str:
    """
    Validates the official Indian PAN format: 5 letters, 4 digits, 1 letter.
    Returns the normalized (uppercase) PAN on success. Raises ValueError on failure.
    `strict=False` (GST_VERIFIED vendors) skips the entity-type and dummy-PAN
    checks below, since a GST-linked PAN is already authoritative.
    """
    if not isinstance(pan_number, str):
        raise ValueError("PAN number must be a string")

    normalized = pan_number.strip().upper()

    if not PAN_REGEX.match(normalized):
        raise ValueError(
            f"Invalid PAN number '{pan_number}': must match the format AAAAA9999A"
        )

    if not strict:
        return normalized

    entity_type_char = normalized[3]
    if entity_type_char not in PAN_ENTITY_TYPE_CODES:
        raise ValueError(
            f"Invalid PAN number '{pan_number}': 4th character '{entity_type_char}' "
            f"is not a recognized entity type"
        )

    letters, digits = normalized[:5], normalized[5:9]
    if len(set(letters)) == 1 or digits == "0000" or normalized in DUMMY_PAN_BLACKLIST:
        raise ValueError(f"PAN number '{pan_number}' looks like a placeholder/dummy PAN")

    return normalized


def validate_email(email: str) -> str:
    if not isinstance(email, str):
        raise ValueError("Email must be a string")

    normalized = email.strip().lower()

    if not EMAIL_REGEX.match(normalized):
        raise ValueError(f"Invalid email address '{email}'")

    if len(normalized) > EMAIL_MAX_LENGTH:
        raise ValueError(f"Email must not exceed {EMAIL_MAX_LENGTH} characters")

    domain = normalized.rsplit("@", 1)[-1]
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        raise ValueError(f"Disposable email domains are not allowed: '{domain}'")

    return normalized


def validate_phone_number(phone_number: str) -> str:
    if not isinstance(phone_number, str):
        raise ValueError("Phone number must be a string")

    normalized = phone_number.strip()

    if not normalized:
        raise ValueError("phone_number is required")

    has_plus = normalized.startswith("+")
    stripped = normalized[1:] if has_plus else normalized
    core = re.sub(r"[\s\-()]", "", stripped)

    if not core.isdigit():
        raise ValueError(f"Invalid phone number '{phone_number}': digits only (optional leading +)")

    if not (PHONE_MIN_DIGITS <= len(core) <= PHONE_MAX_DIGITS):
        raise ValueError(
            f"Invalid phone number '{phone_number}': must have between "
            f"{PHONE_MIN_DIGITS} and {PHONE_MAX_DIGITS} digits"
        )

    if set(core) == {"0"}:
        raise ValueError(f"Invalid phone number '{phone_number}': cannot be all zeros")

    return ("+" if has_plus else "") + core


def validate_ifsc(ifsc_code: str) -> str:
    if not isinstance(ifsc_code, str):
        raise ValueError("IFSC code must be a string")

    normalized = ifsc_code.strip().upper()

    if not IFSC_REGEX.match(normalized):
        raise ValueError(
            f"Invalid IFSC code '{ifsc_code}': must match the format AAAA0XXXXXX"
        )

    return normalized


def validate_bank_account_holder_name(account_holder_name: str) -> str:
    if not isinstance(account_holder_name, str):
        raise ValueError("account_holder_name must be a string")

    normalized = account_holder_name.strip()

    if not normalized:
        raise ValueError("account_holder_name is required for a vendor bank account")

    if len(normalized) < BANK_ACCOUNT_HOLDER_MIN_LENGTH:
        raise ValueError(
            f"account_holder_name must be at least {BANK_ACCOUNT_HOLDER_MIN_LENGTH} characters"
        )

    if len(normalized) > BANK_ACCOUNT_HOLDER_MAX_LENGTH:
        raise ValueError(
            f"account_holder_name must not exceed {BANK_ACCOUNT_HOLDER_MAX_LENGTH} characters"
        )

    if not VENDOR_NAME_CHAR_REGEX.match(normalized):
        raise ValueError(
            "account_holder_name contains invalid characters: only letters, digits, "
            "spaces, and & . , ' - ( ) / are allowed"
        )

    if normalized.replace(" ", "").isdigit():
        raise ValueError("account_holder_name cannot be numeric only")

    return normalized


def validate_bank_account_number(account_number: str) -> str:
    if not isinstance(account_number, str):
        raise ValueError("account_number must be a string")

    normalized = account_number.strip()

    if not normalized.isdigit():
        raise ValueError(f"Invalid account_number '{account_number}': digits only")

    if not (BANK_ACCOUNT_NUMBER_MIN_LENGTH <= len(normalized) <= BANK_ACCOUNT_NUMBER_MAX_LENGTH):
        raise ValueError(
            f"Invalid account_number '{account_number}': must have between "
            f"{BANK_ACCOUNT_NUMBER_MIN_LENGTH} and {BANK_ACCOUNT_NUMBER_MAX_LENGTH} digits"
        )

    return normalized
