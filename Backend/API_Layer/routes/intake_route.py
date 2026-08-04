from fastapi import APIRouter, HTTPException, UploadFile, File
import requests

from Backend.config.env_loader import get_env_var

router = APIRouter()

@router.get("/graph-token")
def get_graph_token():

    tenant_id = get_env_var("TENANT_ID")
    client_id = get_env_var("CLIENT_ID")
    client_secret = get_env_var("CLIENT_SECRET")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
        "scope": "https://graph.microsoft.com/.default"
    }

    response = requests.post(token_url, data=payload)

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.json()
        )

    return response.json()

@router.get("/mails")
def get_mails():

    token = get_graph_token()["access_token"]

    mailbox = get_env_var("MAIL_ADDRESS")      # Replace with your mailbox

    url = (
        f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages"
        "?$top=10"
        "&$select=id,subject,from,receivedDateTime,isRead,hasAttachments"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        # "Prefer": 'outlook.body-content-type="text"'
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.json()
        )

    return response.json()

