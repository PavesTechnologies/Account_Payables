from fastapi import APIRouter, HTTPException, UploadFile, File
import requests
import smtplib
import time
import traceback
from email.message import EmailMessage
from Backend.config.env_loader import get_env_var
from Backend.API_Layer.utils.s3_utils import upload_to_s3, view_from_s3, download_from_s3

router = APIRouter()

EMAIL_USER = get_env_var("EMAIL_USER")
EMAIL_PASSWORD = get_env_var("EMAIL_PASSWORD")
EMAIL_HOST = get_env_var("EMAIL_HOST")
EMAIL_PORT = int(get_env_var("EMAIL_PORT"))

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

@router.post("/send-mail")
# def send_mail(message: dict, to_address:str):
#     token = get_graph_token()["access_token"]
#     sender_address = get_env_var("MAIL_ADDRESS")  # Replace with your sender address

#     url = "https://graph.microsoft.com/v1.0/me/sendMail"

#     headers = {
#         "Authorization": f"Bearer {token}",
#         "Content-Type": "application/json"
#     }

#     payload = {
#         "message": {
#             "subject": message.get("subject", "No Subject"),
#             "body": {
#                 "contentType": "Text",
#                 "content": message.get("body", "")
#             },
#             "toRecipients": [
#                 {
#                     "emailAddress": {
#                         "address": to_address
#                     }
#                 }
#             ]
#         },
#         "saveToSentItems": "true"
#     }

#     response = requests.post(url, headers=headers, json=payload)

#     if response.status_code != 200:
#         raise HTTPException(
#             status_code=response.status_code,
#             detail=response.json()
#         )

#     return response.json()
def send_mail(
    to_mail: str,
    subject: str,
    content: str,
):
    overall_start = time.time()

    try:
        print(f"[EMAIL] Starting email send to {to_mail}")

        msg = EmailMessage()

        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = to_mail

        msg.set_content("This email requires an HTML-supported email client.")

        msg.add_alternative(
            content,
            subtype="html",
        )

        # -----------------------------
        # SMTP CONNECT
        # -----------------------------
        step_start = time.time()

        smtp = smtplib.SMTP(
            EMAIL_HOST,
            EMAIL_PORT,
            timeout=30,
        )

        print(f"[EMAIL] SMTP Connect: " f"{time.time() - step_start:.2f}s")

        # Uncomment if you want SMTP protocol logs
        # smtp.set_debuglevel(1)

        # -----------------------------
        # EHLO
        # -----------------------------
        step_start = time.time()

        smtp.ehlo()

        print(f"[EMAIL] EHLO: " f"{time.time() - step_start:.2f}s")

        # -----------------------------
        # STARTTLS
        # -----------------------------
        step_start = time.time()

        smtp.starttls()

        print(f"[EMAIL] STARTTLS: " f"{time.time() - step_start:.2f}s")

        # -----------------------------
        # EHLO AGAIN
        # -----------------------------
        step_start = time.time()

        smtp.ehlo()

        print(f"[EMAIL] EHLO2: " f"{time.time() - step_start:.2f}s")

        # -----------------------------
        # LOGIN
        # -----------------------------
        step_start = time.time()

        smtp.login(
            EMAIL_USER,
            EMAIL_PASSWORD,
        )

        print(f"[EMAIL] LOGIN: " f"{time.time() - step_start:.2f}s")

        # -----------------------------
        # SEND EMAIL
        # -----------------------------
        step_start = time.time()

        smtp.send_message(msg)

        print(f"[EMAIL] SEND_MESSAGE: " f"{time.time() - step_start:.2f}s")

        # -----------------------------
        # QUIT
        # -----------------------------
        step_start = time.time()

        smtp.quit()

        print(f"[EMAIL] QUIT: " f"{time.time() - step_start:.2f}s")

        print(f"[EMAIL] TOTAL TIME: " f"{time.time() - overall_start:.2f}s")

    except Exception as e:
        print(f"[EMAIL] ERROR: {str(e)}")

        traceback.print_exc()

        print(f"[EMAIL] FAILED AFTER: " f"{time.time() - overall_start:.2f}s")

        raise
