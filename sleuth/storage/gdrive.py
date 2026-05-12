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
DEFAULT_FOLDER_NAME = "Sleuth"


class DriveNotConfigured(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# token i/o
# --------------------------------------------------------------------------- #


def _load_credentials():
    settings = get_settings()
    token_path = settings.drive_token_path
    if not token_path.exists():
        raise DriveNotConfigured(
            "no Drive token. run `sleuth drive login` first."
        )

    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
    except ImportError as e:
        raise DriveNotConfigured(
            "drive deps missing. install with: pip install '.[drive]'"
        ) from e

    creds = Credentials.from_authorized_user_info(
        json.loads(token_path.read_text()), SCOPES
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
        try:
            token_path.chmod(0o600)
        except OSError:
            pass
    return creds


def is_configured() -> bool:
    return get_settings().drive_token_path.exists()


def logout() -> bool:
    """Delete the saved token. Returns True if a token was removed."""
    settings = get_settings()
    if settings.drive_token_path.exists():
        settings.drive_token_path.unlink()
        return True
    return False


# --------------------------------------------------------------------------- #
# auth (new primary entrypoint)
# --------------------------------------------------------------------------- #


def login(
    *,
    explicit_client_secret_path: Optional[Path] = None,
) -> Path:
    """Run device-flow auth using whichever OAuth client is configured.

    Returns the path to the saved token.
    """
    settings = get_settings()
    from sleuth.storage.drive_client import resolve_client, NoClientConfigured
    from sleuth.storage.gdrive_device import (
        device_flow_authorise_with, DeviceFlowError,
    )

    try:
        info = resolve_client(explicit_path=explicit_client_secret_path)
    except NoClientConfigured as e:
        raise DriveNotConfigured(str(e)) from e

    try:
        return device_flow_authorise_with(
            client_id=info.client_id,
            client_secret=info.client_secret,
            token_out=settings.drive_token_path,
        )
    except DeviceFlowError as e:
        raise DriveNotConfigured(f"device flow failed: {e}") from e


# Backward-compat shim used by older code paths.
def authorise_interactive() -> Path:
    return login()


# --------------------------------------------------------------------------- #
# Drive API helpers (account info, folder management)
# --------------------------------------------------------------------------- #


def _drive_service():
    creds = _load_credentials()
    try:
        from googleapiclient.discovery import build  # type: ignore
    except ImportError as e:
        raise DriveNotConfigured(
            "drive deps missing. install with: pip install '.[drive]'"
        ) from e
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def whoami() -> Optional[str]:
    """Return the email address the saved token belongs to, or None."""
    try:
        svc = _drive_service()
        info = svc.about().get(fields="user(emailAddress)").execute()
        return info.get("user", {}).get("emailAddress")
    except Exception:
        return None


def ensure_sleuth_folder(name: str = DEFAULT_FOLDER_NAME) -> str:
    """Find or create a folder by name in My Drive root. Returns its id."""
    svc = _drive_service()
    q = (
        f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' "
        "and 'root' in parents and trashed = false"
    )
    resp = svc.files().list(q=q, fields="files(id, name)", pageSize=1).execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"]
    created = svc.files().create(
        body={"name": name, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return created["id"]


# --------------------------------------------------------------------------- #
# upload
# --------------------------------------------------------------------------- #


def upload_doc(title: str, body_markdown: str) -> str:
    """Upload markdown content as a Google Doc and return its URL."""
    try:
        from googleapiclient.http import MediaIoBaseUpload  # type: ignore
    except ImportError as e:
        raise DriveNotConfigured(
            "drive deps missing. install with: pip install '.[drive]'"
        ) from e

    drive = _drive_service()

    settings = get_settings()
    folder_id = settings.gdrive_folder_id
    if not folder_id:
        # auto-create / find the Sleuth folder so output doesn't sprawl
        try:
            folder_id = ensure_sleuth_folder()
        except Exception:
            folder_id = None  # tolerate failure; just dump in root

    metadata: dict[str, Any] = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
    }
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
