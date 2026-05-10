"""Optional Google Drive sync. Creates a Doc per run.

Setup is lazy: we only import google libraries when this module's functions
are actually called, so the rest of sleuth runs fine without the optional
deps installed.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Optional

from sleuth.config import get_settings


SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class DriveNotConfigured(RuntimeError):
    pass


def _load_credentials():
    settings = get_settings()
    token_path = settings.drive_token_path
    if not token_path.exists():
        raise DriveNotConfigured(
            "Drive token not found. Run `sleuth drive auth` first."
        )

    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
    except ImportError as e:
        raise DriveNotConfigured(
            "Drive deps missing. Install with: pip install '.[drive]'"
        ) from e

    creds = Credentials.from_authorized_user_info(
        json.loads(token_path.read_text()), SCOPES
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    return creds


def authorise_interactive() -> Path:
    """Run the OAuth flow once and persist a token file."""
    settings = get_settings()
    secret = settings.gdrive_client_secret_path
    if not secret or not Path(secret).exists():
        raise DriveNotConfigured(
            "Set GDRIVE_CLIENT_SECRET_PATH in .env to your client_secret*.json."
        )

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
    except ImportError as e:
        raise DriveNotConfigured(
            "Drive deps missing. Install with: pip install '.[drive]'"
        ) from e

    flow = InstalledAppFlow.from_client_secrets_file(secret, SCOPES)
    # Use the console flow so this works on a headless Pi too.
    creds = flow.run_console() if hasattr(flow, "run_console") else flow.run_local_server(port=0)

    settings.drive_token_path.parent.mkdir(parents=True, exist_ok=True)
    settings.drive_token_path.write_text(creds.to_json())
    return settings.drive_token_path


def upload_doc(title: str, body_markdown: str) -> str:
    """Upload markdown content as a Google Doc and return its URL."""
    creds = _load_credentials()

    try:
        from googleapiclient.discovery import build  # type: ignore
        from googleapiclient.http import MediaIoBaseUpload  # type: ignore
    except ImportError as e:
        raise DriveNotConfigured(
            "Drive deps missing. Install with: pip install '.[drive]'"
        ) from e

    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    metadata: dict[str, Any] = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
    }
    folder_id = get_settings().gdrive_folder_id
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaIoBaseUpload(
        io.BytesIO(body_markdown.encode("utf-8")),
        mimetype="text/markdown",
        resumable=False,
    )

    file = drive.files().create(
        body=metadata,
        media_body=media,
        fields="id, webViewLink",
    ).execute()

    return file.get("webViewLink") or f"https://docs.google.com/document/d/{file['id']}"


def is_configured() -> bool:
    return get_settings().drive_token_path.exists()
