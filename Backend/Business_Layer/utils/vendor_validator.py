# Backend/Business_Layer/utils/vendor_validator.py
import re

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_pan(pan_number: str) -> str:
    """
    Validates the official Indian PAN format: 5 letters, 4 digits, 1 letter.
    Returns the normalized (uppercase) PAN on success. Raises ValueError on failure.
    """
    if not isinstance(pan_number, str):
        raise ValueError("PAN number must be a string")

    normalized = pan_number.strip().upper()

    if not PAN_REGEX.match(normalized):
        raise ValueError(
            f"Invalid PAN number '{pan_number}': must match the format AAAAA9999A"
        )

    return normalized


def validate_email(email: str) -> str:
    if not isinstance(email, str):
        raise ValueError("Email must be a string")

    normalized = email.strip()

    if not EMAIL_REGEX.match(normalized):
        raise ValueError(f"Invalid email address '{email}'")

    return normalized
