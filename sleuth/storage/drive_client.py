"""Which OAuth client should we use for Drive auth?

This module is the *single source of truth* for picking the client_id +
client_secret used by `sleuth drive login`.

Resolution order:

  1. Explicit `--client-secrets PATH` argument (passed in as `explicit_path`).
  2. Env vars SLEUTH_GOOGLE_CLIENT_ID + SLEUTH_GOOGLE_CLIENT_SECRET.
  3. Module-level BUILTIN_CLIENT_ID + BUILTIN_CLIENT_SECRET constants.
     The maintainer fills these in to ship a "shared" client so end users
     never have to touch Google Cloud Console.
  4. Legacy GDRIVE_CLIENT_SECRET_PATH env var (per-user client_secret.json).
  5. NoClientConfigured.

For OAuth clients of installed apps, Google explicitly states the
"client_secret" isn't actually a secret — it's distributed in every copy
of the app. So baking it into a published fork is fine.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# --------------------------------------------------------------------------- #
# Maintainer-supplied constants. Fill these in to ship a shared OAuth client
# so users never have to touch Google Cloud Console.
#
# How to create one (Google moved the consent screen into a new "Auth
# Platform" section in 2024, so the URLs below are the current ones):
#   1. Make a project: console.cloud.google.com/projectcreate
#   2. Enable Drive API: console.cloud.google.com/apis/library/drive.googleapis.com
#   3. Configure on Auth Platform: console.cloud.google.com/auth/overview
#        - app name + your email
#        - Audience -> External, then add yourself as a test user
#   4. Create OAuth client: console.cloud.google.com/auth/clients
#        - application type: "TVs and Limited Input devices"
#   5. Copy the client_id and client_secret into the constants below.
#
# Alternatively, set SLEUTH_GOOGLE_CLIENT_ID / SLEUTH_GOOGLE_CLIENT_SECRET
# in your .env — same effect, no code edit, easy to override per machine.
# --------------------------------------------------------------------------- #

BUILTIN_CLIENT_ID = ""
BUILTIN_CLIENT_SECRET = ""


@dataclass(frozen=True)
class ClientInfo:
    client_id: str
    client_secret: str
    source: str  # "env" | "builtin" | "file"
    source_path: Optional[Path] = None


class NoClientConfigured(RuntimeError):
    pass


def _load_secret_file(path: Path) -> tuple[str, str]:
    data = json.loads(path.read_text())
    inner = data.get("installed") or data.get("web") or data
    cid = inner.get("client_id")
    csec = inner.get("client_secret")
    if not cid or not csec:
        raise NoClientConfigured(
            f"{path} is missing client_id or client_secret"
        )
    return cid, csec


def resolve_client(*, explicit_path: Optional[Path] = None) -> ClientInfo:
    """Pick the right OAuth client per the resolution order."""
    # 1. explicit --client-secrets PATH (highest priority)
    if explicit_path is not None:
        p = Path(explicit_path)
        if not p.exists():
            raise NoClientConfigured(f"client secrets file not found: {p}")
        cid, csec = _load_secret_file(p)
        return ClientInfo(cid, csec, source="file", source_path=p)

    # 2. env vars
    env_id = os.environ.get("SLEUTH_GOOGLE_CLIENT_ID", "").strip()
    env_secret = os.environ.get("SLEUTH_GOOGLE_CLIENT_SECRET", "").strip()
    if env_id and env_secret:
        return ClientInfo(env_id, env_secret, source="env")

    # 3. baked-in maintainer constants
    if BUILTIN_CLIENT_ID and BUILTIN_CLIENT_SECRET:
        return ClientInfo(
            BUILTIN_CLIENT_ID, BUILTIN_CLIENT_SECRET, source="builtin",
        )

    # 4. legacy: GDRIVE_CLIENT_SECRET_PATH points at a per-user JSON
    from sleuth.config import get_settings
    settings = get_settings()
    legacy = settings.gdrive_client_secret_path
    if legacy:
        p = Path(legacy).expanduser()
        if p.exists():
            cid, csec = _load_secret_file(p)
            return ClientInfo(cid, csec, source="file", source_path=p)

    raise NoClientConfigured(
        "no Google OAuth client configured. options:\n"
        "  - set SLEUTH_GOOGLE_CLIENT_ID + SLEUTH_GOOGLE_CLIENT_SECRET in .env\n"
        "  - run `sleuth drive login --client-secrets /path/to/secret.json`\n"
        "  - (maintainers) fill in BUILTIN_CLIENT_ID/SECRET in sleuth/storage/drive_client.py"
    )


def has_client() -> bool:
    try:
        resolve_client()
        return True
    except NoClientConfigured:
        return False


def describe_client() -> str:
    """One-line human description of which client is in use."""
    try:
        info = resolve_client()
    except NoClientConfigured:
        return "not configured"
    if info.source == "env":
        return f"from env vars (id: {info.client_id})"
    if info.source == "builtin":
        return f"built-in shared client (id: {info.client_id})"
    if info.source == "file":
        return f"from file {info.source_path} (id: {info.client_id})"
    return f"unknown source (id: {info.client_id})"
