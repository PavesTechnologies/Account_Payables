import os
import requests

from Backend.Business_Layer.utils.sandbox_auth import get_access_token

BASE_URL = os.getenv("SANDBOX_BASE_URL", "https://test-api.sandbox.co.in")
API_KEY = os.getenv("SANDBOX_API_KEY")
API_VERSION = "1.0.0"


def search_gstin(gstin: str):
    """
    Search GST details using GSTIN.
    """

    access_token = get_access_token()

    url = f"{BASE_URL}/gst/compliance/public/gstin/search"

    headers = {
        "Content-Type": "application/json",
        "authorization": access_token,
        "x-api-key": API_KEY,
        "x-api-version": API_VERSION,
    }

    payload = {
        "gstin": gstin
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=30
    )
    print(f"GSTIN Search Response: {response.status_code} - {response.text}")

    response.raise_for_status()

    return response.json()