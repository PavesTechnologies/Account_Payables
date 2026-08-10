import boto3
from botocore.exceptions import ClientError
from fastapi import UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from Backend.config.env_loader import get_env_var
from datetime import datetime


AWS_ACCESS_KEY = get_env_var("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = get_env_var("AWS_SECRET_ACCESS_KEY")
AWS_REGION = get_env_var("AWS_REGION", "ap-south-1")
BUCKET_NAME = get_env_var("AWS_BUCKET_NAME")

# Raise error early if configuration is completely missing
if not all([AWS_ACCESS_KEY, AWS_SECRET_KEY, BUCKET_NAME]):
    raise RuntimeError("Missing required AWS configuration variables in your .env file.")

# Global client initialization
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)



def upload_to_s3(file: UploadFile) -> dict:
    try:
        now = datetime.utcnow()

        s3_key = (
            f"invoices/"
            f"{now.year}/"
            f"{now.month:02d}/"
            f"{file.filename}"
        )

        s3_client.upload_fileobj(
            file.file,
            BUCKET_NAME,
            s3_key,
            ExtraArgs={
                "ContentType": file.content_type
            }
        )

        return {
            "status": "success",
            "filename": file.filename,
            "filepath": s3_key,
        }

    except ClientError as e:
        raise HTTPException(
            status_code=500,
            detail=f"S3 Upload failed: {e.response['Error']['Message']}"
        )


def view_from_s3(filename: str) -> StreamingResponse:
    """Streams data straight to the user browser for an inline file preview."""
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=filename)
        return StreamingResponse(
            response['Body'], 
            media_type=response.get('ContentType', 'application/octet-stream')
        )
    except ClientError as e:
        if e.response['Error']['Code'] == "NoSuchKey":
            raise HTTPException(status_code=404, detail="Requested file does not exist in S3.")
        raise HTTPException(status_code=500, detail=str(e))


def download_from_s3(filename: str) -> StreamingResponse:
    """Streams data with attachment headers to force a browser download box."""
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=filename)
        headers = {"Content-Disposition": f"attachment; filename={filename}"}
        return StreamingResponse(
            response['Body'], 
            media_type="application/octet-stream",
            headers=headers
        )
    except ClientError as e:
        if e.response['Error']['Code'] == "NoSuchKey":
            raise HTTPException(status_code=404, detail="Requested file does not exist in S3.")
        raise HTTPException(status_code=500, detail=str(e))


def delete_from_s3(filename: str) -> dict:
    """Deletes an object permanently from the locked down storage pool."""
    try:
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=filename)
        return {"status": "success", "message": f"Deleted {filename} successfully."}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 Deletion failure: {str(e)}")
