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


PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a .env-style file into {KEY: value}. Strips matched quotes."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and (
            (value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")
        ):
            value = value[1:-1]
            # un-escape any escaped double quotes we wrote
            value = value.replace('\\"', '"').replace("\\\\", "\\")
        out[key] = value
    return out


def has_any_provider(env: dict[str, str]) -> bool:
    """True if at least one provider key is set (and non-empty) in `env`."""
    return any(env.get(var) for var in PROVIDER_ENV_KEYS.values())


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


def _short(value: str, n: int = 8) -> str:
    """For displaying secrets without leaking them: 'sk-abc...wxyz'."""
    if len(value) <= 2 * n:
        return value
    return f"{value[:n]}...{value[-4:]}"


def _keep_replace_remove(
    typer_mod, label: str, current_display: str, *, hide_input: bool = True
) -> tuple[str, str | None]:
    """Show that something is already configured and ask what to do.

    Returns (action, new_value):
      action in {"keep", "replace", "remove"}; new_value only set for replace.
    """
    print_choices = (
        f"  found existing {label} ({current_display}).\n"
        "    [1] keep  [2] replace  [3] remove"
    )
    typer_mod.echo(print_choices)
    raw = typer_mod.prompt("    choice", default="1")
    pick = raw.strip().lower()
    if pick in ("2", "replace", "r"):
        new_val = typer_mod.prompt(
            f"    new {label}",
            hide_input=hide_input,
            default="",
            show_default=False,
        ).strip()
        return ("replace", new_val or None)
    if pick in ("3", "remove", "rm"):
        return ("remove", None)
    return ("keep", None)


def run_wizard(env_path: Path) -> Path:
    """Walk the user through producing a .env file. Returns the written path.

    Reads any existing .env first so already-configured items can be kept or
    cleared without forcing the user to re-paste their keys.
    """
    import typer

    from sleuth.providers import MODEL_CATALOG
    from sleuth.ui import console
    from sleuth.ui.art import banner
    from sleuth.ui.console import bonk, fact, header, tick

    console.print(banner())
    console.print(
        "  let's wire sleuth up. takes about 2 minutes.\n"
        "  things you've already set up are recognised - press 1 to keep them.\n"
    )

    existing = load_env_file(env_path)
    final: dict[str, str] = dict(existing)  # build up the merged result

    # 1. providers
    header("step 1", "model providers")
    for prov in ("openai", "anthropic", "google"):
        var = PROVIDER_ENV_KEYS[prov]
        current = existing.get(var)
        if current:
            action, new_val = _keep_replace_remove(
                typer, f"{prov} api key", _short(current)
            )
            if action == "replace" and new_val:
                final[var] = new_val
                tick(f"  {prov} key replaced.")
            elif action == "remove":
                final.pop(var, None)
                tick(f"  {prov} key removed.")
            # keep: no-op
        else:
            default_yes = (prov == "openai" and not has_any_provider(final))
            if typer.confirm(f"  set up {prov}?", default=default_yes):
                key = typer.prompt(
                    f"    paste your {prov.upper()} api key (input hidden)",
                    hide_input=True,
                ).strip()
                if key:
                    final[var] = key
                    tick(f"  {prov} key captured.")

    if not has_any_provider(final):
        bonk("no providers configured. need at least one to do anything useful.")
        raise typer.Exit(1)

    # 2. default provider/model
    header("step 2", "default provider & model for `ask`")
    available = [
        prov for prov in ("openai", "anthropic", "google")
        if final.get(PROVIDER_ENV_KEYS[prov])
    ]
    current_default_provider = existing.get("SLEUTH_DEFAULT_PROVIDER", "")
    if current_default_provider not in available:
        current_default_provider = available[0]

    if len(available) == 1:
        default_provider = available[0]
        console.print(f"  only {default_provider} configured, defaulting to it.")
    else:
        default_provider = typer.prompt(
            f"  default provider ({'/'.join(available)})",
            default=current_default_provider,
        ).strip()
        if default_provider not in available:
            default_provider = current_default_provider

    final["SLEUTH_DEFAULT_PROVIDER"] = default_provider

    suggested = existing.get("SLEUTH_DEFAULT_MODEL") or DEFAULT_MODEL_FOR[default_provider]
    console.print(f"  available {default_provider} models:")
    for mid, blurb in MODEL_CATALOG[default_provider]:
        marker = " <-" if mid == suggested else "   "
        console.print(f"    {marker} {mid:<26}  {blurb}")
    default_model = typer.prompt("  default model", default=suggested).strip()
    final["SLEUTH_DEFAULT_MODEL"] = default_model

    # 3. notifications
    header("step 3", "notifications (optional)")

    # telegram
    if existing.get("TELEGRAM_BOT_TOKEN"):
        action, new_val = _keep_replace_remove(
            typer, "telegram bot token", _short(existing["TELEGRAM_BOT_TOKEN"])
        )
        if action == "replace" and new_val:
            final["TELEGRAM_BOT_TOKEN"] = new_val
        elif action == "remove":
            final.pop("TELEGRAM_BOT_TOKEN", None)
            final.pop("TELEGRAM_CHAT_ID", None)
        # if keeping token, also let them update chat id
        if action != "remove" and existing.get("TELEGRAM_CHAT_ID"):
            chat_action, chat_val = _keep_replace_remove(
                typer, "telegram chat id", existing["TELEGRAM_CHAT_ID"], hide_input=False,
            )
            if chat_action == "replace" and chat_val:
                final["TELEGRAM_CHAT_ID"] = chat_val
            elif chat_action == "remove":
                final.pop("TELEGRAM_CHAT_ID", None)
    else:
        if typer.confirm("  set up telegram pings?", default=False):
            console.print(
                "    1. message @BotFather on Telegram, send /newbot, copy the token.\n"
                "    2. message your new bot once (any text) so it can DM you.\n"
                "    3. visit https://api.telegram.org/bot<TOKEN>/getUpdates and grab\n"
                "       the chat.id from the JSON."
            )
            tok = typer.prompt("    bot token", default="", show_default=False).strip()
            cid = typer.prompt("    chat id", default="", show_default=False).strip()
            if tok:
                final["TELEGRAM_BOT_TOKEN"] = tok
            if cid:
                final["TELEGRAM_CHAT_ID"] = cid

    # discord
    if existing.get("DISCORD_WEBHOOK_URL"):
        action, new_val = _keep_replace_remove(
            typer, "discord webhook", _short(existing["DISCORD_WEBHOOK_URL"], 24),
            hide_input=False,
        )
        if action == "replace" and new_val:
            final["DISCORD_WEBHOOK_URL"] = new_val
        elif action == "remove":
            final.pop("DISCORD_WEBHOOK_URL", None)
    else:
        if typer.confirm("  set up discord webhook?", default=False):
            console.print(
                "    server -> channel -> Edit Channel -> Integrations -> Webhooks\n"
                "    -> New Webhook -> Copy URL"
            )
            url = typer.prompt("    webhook url", default="", show_default=False).strip()
            if url:
                final["DISCORD_WEBHOOK_URL"] = url

    # 4. drive
    header("step 4", "google drive sync (optional)")
    console.print(
        "  drive sync is wired up separately so we don't slow down setup.\n"
        "  after this finishes, run:  sleuth drive login\n"
        "  that'll show a QR + code; scan with your phone, tap allow, done."
    )

    # 5. global shim — make `sleuth` work from anywhere
    header("step 5", "make `sleuth` work from any directory")
    console.print(
        "  this installs ~/.local/bin/sleuth -> the venv's binary, so you\n"
        "  don't have to cd here and activate the venv every time."
    )
    if typer.confirm("  install the global shim?", default=True):
        from sleuth.installer import (
            default_shim_path, install_shim, local_bin_on_path, sleuth_binary_path,
        )
        try:
            src = sleuth_binary_path()
            if src is None:
                bonk("  no `sleuth` binary in this venv; skipping. run `pip install -e .` first.")
            else:
                result = install_shim(shim_path=default_shim_path(), source=src, force=True)
                tick(f"  shim ready: {result}")
                if not local_bin_on_path():
                    console.print(
                        "  warning: ~/.local/bin is NOT on $PATH. add this to ~/.bashrc:\n"
                        '    export PATH="$HOME/.local/bin:$PATH"\n'
                        "  then run: exec $SHELL -l"
                    )
        except Exception as e:  # noqa: BLE001
            bonk(f"  couldn't install shim: {e}")

    # 6. cron sanity on Linux/Pi
    import platform
    if platform.system() == "Linux":
        header("step 6", "cron daemon")
        from sleuth.installer import cron_status, has_cron_binary
        if not has_cron_binary():
            bonk("  `cron` is not installed. scheduled jobs won't fire.")
            console.print("  fix: sudo apt install cron")
        else:
            cs = cron_status()
            if cs == "active":
                tick("  cron daemon is active.")
            elif cs == "inactive":
                bonk("  cron daemon is installed but NOT RUNNING.")
                console.print("  fix: sudo systemctl enable --now cron")
            else:
                console.print(f"  cron status: {cs} — run `sleuth doctor` later if jobs don't fire.")

    # 7. write
    backup = write_env_file(env_path, final, sections=ENV_SECTIONS)

    console.print()
    tick(f".env written to {env_path}")
    if backup:
        console.print(f"  (your old .env was preserved at {backup.name})")
    console.print()
    console.print(
        "  ready to go. try:\n"
        "    sleuth                  # opens the interactive shell\n"
        "    sleuth ask              # walks you through a one-off\n"
        "    sleuth jobs new         # save a recurring research job\n"
        "    sleuth ping             # test your notifiers"
    )
    if final.get("GDRIVE_CLIENT_SECRET_PATH"):
        console.print("    sleuth drive auth       # finish drive setup")
    return env_path
