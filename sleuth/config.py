"""Settings & paths. Loads from .env, env vars, and (eventually) a config file."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    # sleuth/config.py -> sleuth/ -> project root
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
USER_CONFIG_DIR = Path(os.path.expanduser("~/.config/sleuth"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # provider keys
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")

    # defaults
    default_provider: str = Field(default="openai", alias="SLEUTH_DEFAULT_PROVIDER")
    default_model: str = Field(default="gpt-5.5", alias="SLEUTH_DEFAULT_MODEL")

    # telegram
    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")

    # discord
    discord_webhook_url: Optional[str] = Field(default=None, alias="DISCORD_WEBHOOK_URL")

    # google drive — built-in shared client (if maintainer / user set them)
    google_client_id: Optional[str] = Field(
        default=None, alias="SLEUTH_GOOGLE_CLIENT_ID",
    )
    google_client_secret: Optional[str] = Field(
        default=None, alias="SLEUTH_GOOGLE_CLIENT_SECRET",
    )
    # google drive — legacy per-user secret file (still supported)
    gdrive_client_secret_path: Optional[str] = Field(
        default=None, alias="GDRIVE_CLIENT_SECRET_PATH"
    )
    gdrive_folder_id: Optional[str] = Field(default=None, alias="GDRIVE_FOLDER_ID")

    # paths
    data_dir: Path = Field(default=DEFAULT_DATA_DIR, alias="SLEUTH_DATA_DIR")
    output_dir: Path = Field(default=DEFAULT_OUTPUT_DIR, alias="SLEUTH_OUTPUT_DIR")
    log_dir: Path = Field(default=DEFAULT_LOG_DIR, alias="SLEUTH_LOG_DIR")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "sleuth.db"

    @property
    def drive_token_path(self) -> Path:
        return USER_CONFIG_DIR / "drive_token.json"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.output_dir, self.log_dir, USER_CONFIG_DIR):
            p.mkdir(parents=True, exist_ok=True)


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings
