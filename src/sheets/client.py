"""Klien Google Sheets untuk pencatatan transaksi realtime dan kueri ringkasan."""

from __future__ import annotations

import logging
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from src.config import settings
from src.database import db
from src.models import MonthlySummary, Transaction, TransactionType
from src.sheets.template import (
    setup_dashboard_tab,
    setup_kategori_tab,
    setup_transaksi_tab,
)

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class GoogleSheetsClient:
    """Wrapper klien Google Sheets untuk manajemen transaksi keuangan."""

    def __init__(self) -> None:
        self.spreadsheet_id = settings.google_spreadsheet_id
        self.service_account_file = settings.resolved_service_account_path
        self.tab_transaksi_name = settings.google_sheet_tab_transaksi
        self.tab_kategori_name = settings.google_sheet_tab_kategori
        self.tab_dashboard_name = settings.google_sheet_tab_dashboard

        self._client: Optional[gspread.Client] = None
        self._spreadsheet: Optional[gspread.Spreadsheet] = None

    def is_configured(self) -> bool:
        """Cek apakah konfigurasi Google Sheets sudah lengkap."""
        return settings.is_sheets_configured

    def _get_client(self) -> gspread.Client:
        """Inisialisasi klien gspread dengan Service Account atau OAuth 2.0."""
        if self._client is None:
            # 1. Cek Service Account
            if self.service_account_file.exists():
                creds = Credentials.from_service_account_file(
                    str(self.service_account_file),
                    scopes=SCOPES,
                )
                self._client = gspread.authorize(creds)
                logger.info("Menggunakan autentikasi Google Service Account.")
            # 2. Cek OAuth 2.0 (authorized_user.json atau client_secret.json)
            elif (
                settings.resolved_authorized_user_path.exists()
                or settings.google_authorized_user_json
                or settings.resolved_client_secret_path.exists()
                or (settings.google_oauth_client_id and settings.google_oauth_client_secret)
            ):
                # Tulis authorized_user.json jika diberikan via Environment Variable (misal di Render/Cloud)
                if not settings.resolved_authorized_user_path.exists() and settings.google_authorized_user_json:
                    settings.resolved_authorized_user_path.parent.mkdir(parents=True, exist_ok=True)
                    settings.resolved_authorized_user_path.write_text(settings.google_authorized_user_json.strip())

                # Buat client_secret.json otomatis jika ID & secret diisi langsung di .env
                if not settings.resolved_client_secret_path.exists() and settings.google_oauth_client_id and settings.google_oauth_client_secret:
                    settings.resolved_client_secret_path.parent.mkdir(parents=True, exist_ok=True)
                    import json
                    oauth_data = {
                        "installed": {
                            "client_id": settings.google_oauth_client_id,
                            "client_secret": settings.google_oauth_client_secret,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "redirect_uris": ["http://localhost"],
                        }
                    }
                    settings.resolved_client_secret_path.write_text(json.dumps(oauth_data, indent=2))

                self._client = gspread.oauth(
                    credentials_filename=str(settings.resolved_client_secret_path),
                    authorized_user_filename=str(settings.resolved_authorized_user_path),
                    scopes=SCOPES,
                )
                logger.info("Menggunakan autentikasi Google OAuth 2.0.")
            else:
                raise FileNotFoundError(
                    f"Kredensial Google Sheets tidak ditemukan. Letakkan service_account.json atau client_secret.json di credentials/"
                )
        return self._client

    def _get_spreadsheet(self) -> gspread.Spreadsheet:
        """Buka spreadsheet berdasarkan ID."""
        if self._spreadsheet is None:
            client = self._get_client()
            self._spreadsheet = client.open_by_key(self.spreadsheet_id)
        return self._spreadsheet

    def initialize_sheets(self) -> None:
        """Inisialisasi seluruh tab worksheet jika belum tersedia."""
        if not self.is_configured():
            logger.warning("Google Sheets belum dikonfigurasi. Inisialisasi dilewati.")
            return

        ss = self._get_spreadsheet()
        existing_tabs = [w.title for w in ss.worksheets()]

        # 1. Tab Transaksi
        if self.tab_transaksi_name not in existing_tabs:
            ws_transaksi = ss.add_worksheet(title=self.tab_transaksi_name, rows=1000, cols=15)
        else:
            ws_transaksi = ss.worksheet(self.tab_transaksi_name)
        setup_transaksi_tab(ws_transaksi)

        # 2. Tab Kategori
        if self.tab_kategori_name not in existing_tabs:
            ws_kategori = ss.add_worksheet(title=self.tab_kategori_name, rows=100, cols=10)
        else:
            ws_kategori = ss.worksheet(self.tab_kategori_name)
        setup_kategori_tab(ws_kategori)

        # 3. Tab Dashboard
        if self.tab_dashboard_name not in existing_tabs:
            ws_dashboard = ss.add_worksheet(title=self.tab_dashboard_name, rows=100, cols=10)
        else:
            ws_dashboard = ss.worksheet(self.tab_dashboard_name)
        setup_dashboard_tab(ws_dashboard, self.tab_transaksi_name)

        logger.info("Inisialisasi tab Google Sheets berhasil.")

    def append_transaction(self, tx: Transaction) -> bool:
        """Menambahkan baris transaksi baru ke tab Transaksi di Google Sheets secara realtime."""
        # Selalu simpan juga ke database SQLite lokal
        db.save_transaction(tx)

        if not self.is_configured() or settings.mock_mode:
            logger.info(f"[MOCK/LOCAL] Transaksi dicatat ke DB lokal: {tx.formatted_amount} ({tx.description})")
            return True

        try:
            ss = self._get_spreadsheet()
            ws = ss.worksheet(self.tab_transaksi_name)
            row_data = tx.to_sheet_row()
            ws.append_row(row_data, value_input_option="USER_ENTERED")
            logger.info(f"Transaksi {tx.id} berhasil dicatat ke Google Sheets.")
            return True
        except Exception as e:
            logger.error(f"Gagal mencatat transaksi ke Google Sheets: {e}", exc_info=True)
            return False

    def update_transaction_category(self, tx_id: str, new_category: str) -> bool:
        """Memperbarui kategori suatu transaksi di Google Sheets & database lokal."""
        db.update_transaction_category(tx_id, new_category)

        if not self.is_configured() or settings.mock_mode:
            return True

        try:
            ss = self._get_spreadsheet()
            ws = ss.worksheet(self.tab_transaksi_name)
            # Cari baris yang kolom A (ID) cocok dengan tx_id
            cell = ws.find(tx_id, in_column=1)
            if cell:
                # Kolom F adalah Kategori (kolom 6)
                ws.update_cell(cell.row, 6, new_category)
                logger.info(f"Kategori transaksi {tx_id} diperbarui menjadi '{new_category}'.")
                return True
            return False
        except Exception as e:
            logger.error(f"Gagal memperbarui kategori transaksi {tx_id}: {e}", exc_info=True)
            return False

    def get_monthly_summary(self, year: int, month: int) -> MonthlySummary:
        """Mengambil rekapitulasi bulanan.

        Menggunakan database lokal sebagai sumber data yang cepat dan andal.
        """
        return db.get_monthly_summary(year, month)


# Singleton instance
sheets_client = GoogleSheetsClient()
