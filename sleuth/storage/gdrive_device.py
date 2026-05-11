"""Google's Device Authorization Grant flow for Drive (RFC 8628).

Why this and not InstalledAppFlow.run_local_server()? On a headless Pi
there's no browser to open. Device flow shows you a URL + 8-character
code, you authorize on your phone or laptop, and the Pi polls until
Google says yes. Same flow GitHub CLI uses.

Pure helpers (_extract_client_info, _build_credentials_payload,
_classify_poll_response, _device_code_payload, _poll_payload) are
unit-tested. The polling loop itself is exercised by hand.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import httpx


DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class DeviceFlowError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #


def _extract_client_info(data: dict[str, Any]) -> tuple[str, str]:
    """Pull (client_id, client_secret) from a Google client_secret*.json blob.

    The file may be wrapped in {"installed": ...} or {"web": ...}, or bare.
    """
    inner = data.get("installed") or data.get("web") or data
    cid = inner.get("client_id")
    csec = inner.get("client_secret")
    if not cid or not csec:
        raise ValueError(
            "client_secret JSON is missing client_id or client_secret. "
            "Did you download the right file from Google Cloud Console?"
        )
    return cid, csec


def _device_code_payload(client_id: str) -> dict[str, str]:
    return {"client_id": client_id, "scope": " ".join(SCOPES)}


def _poll_payload(*, client_id: str, client_secret: str, device_code: str) -> dict[str, str]:
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }


def _build_credentials_payload(
    token_response: dict[str, Any],
    *,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Convert a device-flow token response to google-auth's saved-creds shape."""
    payload: dict[str, Any] = {
        "token": token_response.get("access_token"),
        "token_uri": TOKEN_URL,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": (token_response.get("scope") or "").split() or list(SCOPES),
    }
    if "refresh_token" in token_response:
        payload["refresh_token"] = token_response["refresh_token"]
    return payload


def _classify_poll_response(status: int, body: dict[str, Any]) -> tuple[str, Any]:
    """Translate a token-endpoint response to (kind, payload-or-msg).

    Kinds: 'success' | 'pending' | 'slow_down' | 'denied' | 'expired' | 'failed'.
    """
    if status == 200 and "access_token" in body:
        return "success", body
    err = body.get("error", "")
    msg = body.get("error_description") or err
    if err == "authorization_pending":
        return "pending", None
    if err == "slow_down":
        return "slow_down", None
    if err == "access_denied":
        return "denied", f"user denied authorization ({msg})"
    if err == "expired_token":
        return "expired", f"verification window expired ({msg})"
    return "failed", f"google said: {err or 'unknown error'} - {msg}"


def render_qr_ascii(data: str) -> str:
    """Render `data` as a QR code using unicode block characters."""
    import io
    import qrcode

    qr = qrcode.QRCode(border=1, box_size=1)
    qr.add_data(data)
    qr.make(fit=True)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# the actual flow
# --------------------------------------------------------------------------- #


def request_device_code(client_id: str, *, http: Optional[httpx.Client] = None) -> dict[str, Any]:
    """Ask Google for a device_code + user_code + verification_url."""
    client = http or httpx
    resp = client.post(DEVICE_CODE_URL, data=_device_code_payload(client_id), timeout=20.0)
    if resp.status_code != 200:
        raise DeviceFlowError(
            f"device_code request failed ({resp.status_code}): {resp.text[:300]}"
        )
    return resp.json()


def poll_for_token(
    *,
    client_id: str,
    client_secret: str,
    device_code: str,
    initial_interval: int = 5,
    deadline: float,
    http: Optional[httpx.Client] = None,
    sleep=time.sleep,
) -> dict[str, Any]:
    """Poll Google's token endpoint until the user authorises or we time out."""
    client = http or httpx
    interval = max(1, initial_interval)
    while time.time() < deadline:
        sleep(interval)
        resp = client.post(
            TOKEN_URL,
            data=_poll_payload(
                client_id=client_id, client_secret=client_secret,
                device_code=device_code,
            ),
            timeout=20.0,
        )
        try:
            body = resp.json()
        except json.JSONDecodeError:
            body = {}
        kind, payload = _classify_poll_response(resp.status_code, body)
        if kind == "success":
            return payload
        if kind == "pending":
            continue
        if kind == "slow_down":
            interval += 5
            continue
        # denied / expired / failed
        raise DeviceFlowError(payload)
    raise DeviceFlowError("verification window expired without authorization")


def device_flow_authorise(client_secret_path: Path, token_out: Path) -> Path:
    """Run the whole flow and write the resulting token to `token_out`.

    Returns `token_out` on success. Prints the user code + a QR for the
    verification URL while polling.
    """
    from sleuth.ui import console
    from sleuth.ui.console import bonk, tick
    from rich.text import Text

    data = json.loads(Path(client_secret_path).read_text())
    client_id, client_secret = _extract_client_info(data)

    flow = request_device_code(client_id)
    user_code = flow["user_code"]
    verification_url = flow.get("verification_url") or flow.get("verification_uri")
    verification_url_complete = flow.get("verification_url_complete") or flow.get("verification_uri_complete")
    interval = int(flow.get("interval", 5))
    expires_in = int(flow.get("expires_in", 1800))

    qr_target = verification_url_complete or verification_url
    qr = render_qr_ascii(qr_target)

    console.print()
    console.print(Text("  authorise sleuth on your Google account:", style="header"))
    console.print()
    console.print(Text(qr, style="paper"))
    console.print(Text(f"  scan the QR above, or open: {verification_url}", style="muted"))
    console.print(Text(f"  and enter this code:  ", style="muted") + Text(user_code, style="header"))
    console.print()
    console.print(Text(
        f"  waiting up to {expires_in // 60} min for you to authorise...",
        style="info",
    ))

    deadline = time.time() + expires_in
    try:
        token_resp = poll_for_token(
            client_id=client_id,
            client_secret=client_secret,
            device_code=flow["device_code"],
            initial_interval=interval,
            deadline=deadline,
        )
    except DeviceFlowError as e:
        bonk(str(e))
        raise

    payload = _build_credentials_payload(
        token_resp, client_id=client_id, client_secret=client_secret,
    )
    token_out.parent.mkdir(parents=True, exist_ok=True)
    token_out.write_text(json.dumps(payload, indent=2))
    tick(f"token saved to {token_out}")
    return token_out
