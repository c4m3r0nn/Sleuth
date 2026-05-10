"""First-run wizard. Walks newcomers through .env in plain English.

The pure functions here (write_env_file, plan_env_from_answers) are unit-
tested. The interactive part lives at the bottom and is wired into the CLI.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

# --------------------------------------------------------------------------- #
# pure helpers (testable)
# --------------------------------------------------------------------------- #


def _quote(value: str) -> str:
    """Quote a .env value if it contains anything risky."""
    if any(ch in value for ch in (" ", "\t", "#", "'", '"')):
        # escape any embedded double quotes, then wrap
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def write_env_file(
    path: Path,
    values: dict[str, Optional[str]],
    *,
    sections: Optional[list[tuple[str, list[str]]]] = None,
    backup: bool = True,
) -> Optional[Path]:
    """Write .env-format pairs to `path`. Returns the backup path if one was made.

    Empty or None values are dropped. If `sections` is supplied it dictates
    grouping: [(header, [key, ...]), ...]. Keys not listed in any section are
    appended at the end.
    """
    backup_path: Optional[Path] = None
    if path.exists() and backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_path = path.with_name(f"{path.name}.bak.{ts}")
        shutil.copy2(path, backup_path)

    written_keys: set[str] = set()
    lines: list[str] = []

    if sections:
        for header, keys in sections:
            section_lines: list[str] = []
            for k in keys:
                v = values.get(k)
                if v in (None, ""):
                    continue
                section_lines.append(f"{k}={_quote(str(v))}")
                written_keys.add(k)
            if section_lines:
                if lines:
                    lines.append("")
                lines.append(f"# {header}")
                lines.extend(section_lines)

    leftovers: list[str] = []
    for k, v in values.items():
        if k in written_keys:
            continue
        if v in (None, ""):
            continue
        leftovers.append(f"{k}={_quote(str(v))}")
    if leftovers:
        if lines:
            lines.append("")
        if sections:
            lines.append("# other")
        lines.extend(leftovers)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return backup_path


def plan_env_from_answers(
    *,
    providers: dict[str, str],
    default_provider: str,
    default_model: str,
    telegram_token: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
    discord_webhook: Optional[str] = None,
    gdrive_client_secret_path: Optional[str] = None,
    gdrive_folder_id: Optional[str] = None,
) -> dict[str, str]:
    """Convert wizard answers into the dict that write_env_file consumes."""
    out: dict[str, str] = {}

    key_for_provider = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
    }
    for prov, key in providers.items():
        if not key:
            continue
        var = key_for_provider.get(prov)
        if var:
            out[var] = key

    out["SLEUTH_DEFAULT_PROVIDER"] = default_provider
    out["SLEUTH_DEFAULT_MODEL"] = default_model

    if telegram_token:
        out["TELEGRAM_BOT_TOKEN"] = telegram_token
    if telegram_chat_id:
        out["TELEGRAM_CHAT_ID"] = str(telegram_chat_id)
    if discord_webhook:
        out["DISCORD_WEBHOOK_URL"] = discord_webhook
    if gdrive_client_secret_path:
        out["GDRIVE_CLIENT_SECRET_PATH"] = gdrive_client_secret_path
    if gdrive_folder_id:
        out["GDRIVE_FOLDER_ID"] = gdrive_folder_id

    return out


ENV_SECTIONS: list[tuple[str, list[str]]] = [
    ("providers", ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"]),
    ("defaults", ["SLEUTH_DEFAULT_PROVIDER", "SLEUTH_DEFAULT_MODEL"]),
    ("telegram", ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]),
    ("discord", ["DISCORD_WEBHOOK_URL"]),
    ("google drive", ["GDRIVE_CLIENT_SECRET_PATH", "GDRIVE_FOLDER_ID"]),
]


# --------------------------------------------------------------------------- #
# interactive flow
# --------------------------------------------------------------------------- #


# default model per provider (handy when only one provider is selected)
DEFAULT_MODEL_FOR = {
    "openai": "gpt-5.5",
    "anthropic": "claude-opus-4-7",
    "google": "gemini-3.1-pro-preview",
}


def run_wizard(env_path: Path) -> Path:
    """Walk the user through producing a .env file. Returns the written path.

    Imports prompt helpers lazily so the pure helpers above don't pull in typer.
    """
    import typer

    from sleuth.providers import MODEL_CATALOG
    from sleuth.ui import console
    from sleuth.ui.art import banner
    from sleuth.ui.console import bonk, fact, header, tick

    console.print(banner())
    console.print(
        "  let's wire sleuth up. takes about 2 minutes.\n"
        "  press enter to skip anything you don't want.\n"
    )

    # 1. providers
    header("step 1", "which model providers do you have keys for?")
    providers: dict[str, str] = {}
    for prov in ("openai", "anthropic", "google"):
        if typer.confirm(f"  set up {prov}?", default=(prov == "openai")):
            key = typer.prompt(
                f"    paste your {prov.upper()} api key (input hidden)",
                hide_input=True,
            )
            if key.strip():
                providers[prov] = key.strip()
                tick(f"  {prov} key captured.")
    if not providers:
        bonk("you need at least one provider. bailing.")
        raise typer.Exit(1)

    # 2. default provider/model
    header("step 2", "pick the default for `sleuth ask`")
    if len(providers) == 1:
        default_provider = next(iter(providers))
        console.print(f"  only one provider, defaulting to {default_provider}.")
    else:
        choices = list(providers.keys())
        default_provider = typer.prompt(
            f"  default provider ({'/'.join(choices)})",
            default=choices[0],
        )
        if default_provider not in providers:
            default_provider = choices[0]

    suggested = DEFAULT_MODEL_FOR[default_provider]
    console.print(f"  available {default_provider} models:")
    for mid, blurb in MODEL_CATALOG[default_provider]:
        marker = " <-" if mid == suggested else "   "
        console.print(f"    {marker} {mid:<26}  {blurb}")
    default_model = typer.prompt("  default model", default=suggested)

    # 3. notifications
    header("step 3", "notifications (optional)")
    telegram_token = telegram_chat_id = None
    if typer.confirm("  set up telegram pings?", default=False):
        console.print(
            "    1. message @BotFather on Telegram, send /newbot, copy the token.\n"
            "    2. message your new bot once (any text) so it can DM you.\n"
            "    3. visit https://api.telegram.org/bot<TOKEN>/getUpdates and grab"
            "       the chat.id from the JSON."
        )
        telegram_token = (typer.prompt("    bot token", default="") or "").strip() or None
        telegram_chat_id = (typer.prompt("    chat id", default="") or "").strip() or None

    discord_webhook = None
    if typer.confirm("  set up discord webhook?", default=False):
        console.print(
            "    server -> channel -> Edit Channel -> Integrations -> Webhooks\n"
            "    -> New Webhook -> Copy URL"
        )
        discord_webhook = (typer.prompt("    webhook url", default="") or "").strip() or None

    # 4. drive
    header("step 4", "google drive sync (optional)")
    drive_secret = drive_folder = None
    if typer.confirm("  point me at a Drive client_secret.json?", default=False):
        console.print(
            "    if you don't have one yet, see\n"
            "    https://developers.google.com/workspace/guides/create-credentials"
        )
        drive_secret = (typer.prompt("    path to client_secret*.json", default="") or "").strip() or None
        drive_folder = (typer.prompt("    parent Drive folder id (blank for root)", default="") or "").strip() or None

    # 5. write
    plan = plan_env_from_answers(
        providers=providers,
        default_provider=default_provider,
        default_model=default_model,
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
        discord_webhook=discord_webhook,
        gdrive_client_secret_path=drive_secret,
        gdrive_folder_id=drive_folder,
    )

    backup = write_env_file(env_path, plan, sections=ENV_SECTIONS)

    console.print()
    tick(f".env written to {env_path}")
    if backup:
        console.print(f"  (your old .env was preserved at {backup.name})")
    console.print()
    console.print(
        "  ready to go. try:\n"
        "    sleuth ask \"what's a positive news story from today?\"\n"
        "    sleuth jobs new\n"
        "    sleuth ping"
    )
    if drive_secret:
        console.print("    sleuth drive auth   # to finish drive setup")
    return env_path
