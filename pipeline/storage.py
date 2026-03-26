import os
from datetime import datetime, timedelta, timezone

from azure.storage.blob import (
    BlobServiceClient,
    BlobSasPermissions,
    generate_blob_sas,
)

blob_service = BlobServiceClient.from_connection_string(
    os.environ["AZURE_STORAGE_CONN"]
)
CONTAINER = "pdfs"


def upload_pdf(job_id: str, pdf_bytes: bytes) -> str:
    """Upload PDF bytes to Azure Blob Storage and return a signed URL valid for 2 hours."""
    blob_name = f"resumes/{job_id}.pdf"
    container_client = blob_service.get_container_client(CONTAINER)

    container_client.upload_blob(
        name=blob_name,
        data=pdf_bytes,
        overwrite=True,
        content_settings={"content_type": "application/pdf"},
    )

    sas_token = generate_blob_sas(
        account_name=os.environ["AZURE_STORAGE_ACCOUNT"],
        container_name=CONTAINER,
        blob_name=blob_name,
        account_key=os.environ["AZURE_STORAGE_KEY"],
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=2),
    )

    base_url = f"https://{os.environ['AZURE_STORAGE_ACCOUNT']}.blob.core.windows.net"
    return f"{base_url}/{CONTAINER}/{blob_name}?{sas_token}"
