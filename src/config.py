"""Konfigurasi aplikasi dan pemuatan environment variable."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Set

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Pengaturan konfigurasi aplikasi."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 1. Telegram Bot
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    allowed_telegram_user_ids: str = Field(default="", alias="ALLOWED_TELEGRAM_USER_IDS")
    auto_confirm_screenshot: bool = Field(default=False, alias="AUTO_CONFIRM_SCREENSHOT")

    # 2. Google Sheets (Mendukung Service Account & OAuth 2.0)
    google_service_account_file: str = Field(
        default="credentials/service_account.json",
        alias="GOOGLE_SERVICE_ACCOUNT_FILE",
    )
    google_oauth_client_id: str = Field(
        default="",
        alias="GOOGLE_OAUTH_CLIENT_ID",
    )
    google_oauth_client_secret: str = Field(
        default="",
        alias="GOOGLE_OAUTH_CLIENT_SECRET",
    )
    google_client_secret_file: str = Field(
        default="credentials/client_secret.json",
        alias="GOOGLE_CLIENT_SECRET_FILE",
    )
    google_authorized_user_file: str = Field(
        default="credentials/authorized_user.json",
        alias="GOOGLE_AUTHORIZED_USER_FILE",
    )
    google_authorized_user_json: str = Field(
        default="",
        alias="GOOGLE_AUTHORIZED_USER_JSON",
    )
    google_spreadsheet_id: str = Field(default="", alias="GOOGLE_SPREADSHEET_ID")
    google_sheet_tab_transaksi: str = Field(
        default="Transaksi",
        alias="GOOGLE_SHEET_TAB_TRANSAKSI",
    )
    google_sheet_tab_kategori: str = Field(
        default="Kategori",
        alias="GOOGLE_SHEET_TAB_KATEGORI",
    )
    google_sheet_tab_dashboard: str = Field(
        default="Dashboard",
        alias="GOOGLE_SHEET_TAB_DASHBOARD",
    )

    # 3. Email IMAP (Livin Mandiri)
    email_imap_server: str = Field(default="imap.gmail.com", alias="EMAIL_IMAP_SERVER")
    email_imap_port: int = Field(default=993, alias="EMAIL_IMAP_PORT")
    email_imap_user: str = Field(default="", alias="EMAIL_IMAP_USER")
    email_imap_password: str = Field(default="", alias="EMAIL_IMAP_PASSWORD")
    email_check_interval_seconds: int = Field(
        default=30,
        alias="EMAIL_CHECK_INTERVAL_SECONDS",
    )
    email_imap_folder: str = Field(default="INBOX", alias="EMAIL_IMAP_FOLDER")
    email_mandiri_sender: str = Field(
        default="noreply@bankmandiri.co.id",
        alias="EMAIL_MANDIRI_SENDER",
    )

    # 4. OCR & Vision AI (Gemini / Ollama)
    ocr_provider: str = Field(default="gemini", alias="OCR_PROVIDER")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.6-flash", alias="GEMINI_MODEL")

    # 4.b Ollama Local Vision
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.2-vision", alias="OLLAMA_MODEL")

    # 5. General & Server Port
    port: int = Field(default=10000, alias="PORT")
    mock_mode: bool = Field(default=False, alias="MOCK_MODE")
    database_path: str = Field(default="data/finance.db", alias="DATABASE_PATH")
    timezone: str = Field(default="Asia/Jakarta", alias="TIMEZONE")

    @property
    def allowed_user_ids(self) -> Set[int]:
        """Kumpulan Telegram User ID yang memiliki izin akses."""
        if not self.allowed_telegram_user_ids:
            return set()
        ids = set()
        for item in self.allowed_telegram_user_ids.split(","):
            item = item.strip()
            if item.isdigit():
                ids.add(int(item))
        return ids

    def is_user_allowed(self, user_id: int) -> bool:
        """Cek apakah suatu Telegram user_id diizinkan."""
        # Jika tidak ada yang didefinisikan, perbolehkan semua untuk kemudahan setup pertama kali
        allowed = self.allowed_user_ids
        if not allowed:
            return True
        return user_id in allowed

    @property
    def resolved_service_account_path(self) -> Path:
        """Path absolut ke berkas service_account.json."""
        p = Path(self.google_service_account_file)
        if not p.is_absolute():
            return BASE_DIR / p
        return p

    @property
    def resolved_client_secret_path(self) -> Path:
        """Path absolut ke berkas client_secret.json (OAuth 2.0)."""
        p = Path(self.google_client_secret_file)
        if not p.is_absolute():
            return BASE_DIR / p
        return p

    @property
    def resolved_authorized_user_path(self) -> Path:
        """Path absolut ke token user yang telah diotorisasi."""
        p = Path(self.google_authorized_user_file)
        if not p.is_absolute():
            return BASE_DIR / p
        return p

    @property
    def resolved_database_path(self) -> Path:
        """Path absolut ke database SQLite."""
        p = Path(self.database_path)
        if not p.is_absolute():
            return BASE_DIR / p
        return p

    @property
    def is_telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_bot_token != "your_telegram_bot_token_here")

    @property
    def is_sheets_configured(self) -> bool:
        has_id = bool(self.google_spreadsheet_id and self.google_spreadsheet_id != "your_google_spreadsheet_id_here")
        has_auth = (
            self.resolved_service_account_path.exists()
            or self.resolved_client_secret_path.exists()
            or (bool(self.google_oauth_client_id) and bool(self.google_oauth_client_secret))
        )
        return has_id and has_auth

    @property
    def is_email_configured(self) -> bool:
        return bool(
            self.email_imap_user
            and self.email_imap_password
            and self.email_imap_password != "your_16_char_app_password"
        )

    @property
    def is_gemini_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key != "your_gemini_api_key_here")


# Singleton instance
settings = Settings()
