import os
import requests

BASE_URL = os.getenv("SANDBOX_BASE_URL", "https://test-api.sandbox.co.in")
API_KEY = os.getenv("SANDBOX_API_KEY")
API_SECRET = os.getenv("SANDBOX_API_SECRET")
API_VERSION = "1.0.0"


def get_access_token() -> str:
    """
    Authenticate with Sandbox and return JWT access token.
    """

    url = f"{BASE_URL}/authenticate"

    headers = {
        "x-api-key": API_KEY,
        "x-api-secret": API_SECRET,
        "x-api-version": API_VERSION,
    }

    response = requests.post(url, headers=headers, timeout=30)

    response.raise_for_status()

    data = response.json()

    return data["data"]["access_token"]