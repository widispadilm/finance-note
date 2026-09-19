"""Orkestrator alur transaksi: menggabungkan Email, OCR, Sheets, dan Telegram Bot."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Optional

from telegram import Bot

from src.config import settings
from src.core.categorizer import guess_category
from src.database import db
from src.models import (
    Transaction,
    TransactionSource,
    TransactionType,
    parse_rupiah_string,
)
from src.ocr.base import BaseOcrEngine
from src.ocr.gemini_vision import GeminiVisionEngine
from src.ocr.mock_engine import MockOcrEngine
from src.ocr.ollama_vision import OllamaVisionEngine
from src.sheets.client import GoogleSheetsClient, sheets_client
from src.telegram_bot.formatters import (
    build_saved_transaction_keyboard,
    format_transaction_card,
)

logger = logging.getLogger(__name__)


class FinanceEngine:
    """Mesin utama orkestrasi pencatatan keuangan."""

    def __init__(
        self,
        sheets: Optional[GoogleSheetsClient] = None,
        ocr: Optional[BaseOcrEngine] = None,
    ) -> None:
        self.sheets = sheets or sheets_client

        if ocr is not None:
            self.ocr = ocr
        elif settings.mock_mode:
            logger.info("Menggunakan MockOcrEngine untuk pemrosesan gambar.")
            self.ocr = MockOcrEngine()
        elif settings.ocr_provider.lower() == "ollama":
            logger.info(f"Menggunakan OllamaVisionEngine ({settings.ollama_model}) pada {settings.ollama_base_url}.")
            self.ocr = OllamaVisionEngine()
        elif settings.is_gemini_configured:
            logger.info(f"Menggunakan GeminiVisionEngine ({settings.gemini_model}).")
            self.ocr = GeminiVisionEngine()
        else:
            logger.info("Tidak ada API key Gemini atau Ollama provider. Menggunakan MockOcrEngine.")
            self.ocr = MockOcrEngine()

        self._telegram_bot: Optional[Bot] = None

    def set_telegram_bot(self, bot: Bot) -> None:
        """Menyimpan referensi bot Telegram untuk mengirim notifikasi proaktif."""
        self._telegram_bot = bot

    # --- 1. Pemrosesan Transaksi dari Email Livin Mandiri ---

    async def process_email_transaction(self, tx: Transaction) -> bool:
        """Memproses transaksi yang didapatkan dari email notifikasi Livin Mandiri."""
        logger.info(f"Memproses transaksi email Mandiri: {tx.formatted_amount} - {tx.description}")

        # Cek deduplikasi referensi
        if db.is_transaction_duplicate(tx.reference_id, tx.amount, tx.date):
            logger.info(f"Transaksi {tx.reference_id} sudah pernah dicatat sebelumnya. Dilewati.")
            return False

        # Catat ke Google Sheets & DB lokal
        success = self.sheets.append_transaction(tx)
        tx.status = "TERCATAT" if success else "GAGAL_SYNC"
        db.save_transaction(tx)

        # Kirim notifikasi realtime ke Telegram pengguna jika bot aktif
        if self._telegram_bot and settings.is_telegram_configured:
            message_text = format_transaction_card(
                tx,
                title="Notifikasi Transaksi Livin' Mandiri",
                is_saved=success,
            )
            keyboard = build_saved_transaction_keyboard(tx.id)

            for user_id in settings.allowed_user_ids:
                try:
                    await self._telegram_bot.send_message(
                        chat_id=user_id,
                        text=message_text,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                    )
                except Exception as ex:
                    logger.error(f"Gagal mengirim notifikasi Telegram ke {user_id}: {ex}")

        return success

    # --- 2. Pemrosesan Screenshot dari Telegram Bot (GoPay dll) ---

    async def process_screenshot(
        self,
        image_bytes: bytes,
        user_id: int,
        mime_type: str = "image/jpeg",
    ) -> tuple[Optional[Transaction], str]:
        """Memproses gambar screenshot yang dikirim pengguna via Telegram."""
        tx = await self.ocr.extract_transaction(image_bytes, mime_type=mime_type)
        if not tx:
            return None, "Gagal mengekstrak data dari screenshot. Pastikan gambar bukti pembayaran terlihat jelas."

        # Cek apakah mode auto-confirm aktif
        if settings.auto_confirm_screenshot:
            success = self.sheets.append_transaction(tx)
            tx.status = "TERCATAT" if success else "GAGAL_SYNC"
            db.save_transaction(tx)
            return tx, "saved" if success else "failed_sync"

        # Simpan sebagai aksi tertunda menunggu konfirmasi tombol
        action_id = uuid.uuid4().hex[:10]
        db.save_pending_action(action_id, user_id, tx)
        return tx, action_id

    async def confirm_and_save_transaction(self, action_id: str) -> Optional[Transaction]:
        """Konfirmasi simpan transaksi yang tertunda ke Google Sheets."""
        tx = db.get_pending_action(action_id)
        if not tx:
            return None

        success = self.sheets.append_transaction(tx)
        tx.status = "TERCATAT" if success else "GAGAL_SYNC"
        db.save_transaction(tx)
        db.delete_pending_action(action_id)
        return tx

    def cancel_pending_transaction(self, action_id: str) -> bool:
        """Batalkan transaksi yang tertunda."""
        tx = db.get_pending_action(action_id)
        if tx:
            db.delete_pending_action(action_id)
            return True
        return False

    def update_pending_category(self, action_id: str, new_category: str) -> Optional[Transaction]:
        """Ubah kategori pada transaksi yang masih menunggu konfirmasi."""
        tx = db.get_pending_action(action_id)
        if not tx:
            return None
        tx.category = new_category
        # Update json di pending_actions
        db.save_pending_action(action_id, 0, tx)
        return tx

    # --- 3. Pemrosesan Input Teks Manual / Bahasa Alami ---

    def parse_manual_text(self, text: str) -> Optional[Transaction]:
        """Parsing input teks manual atau bahasa alami pengguna.

        Contoh yang didukung:
        - '/keluar 35000 Makan siang (GoPay)'
        - '/masuk 5000000 Gaji bulanan'
        - 'makan bakso 25rb gopay'
        - 'bensin 50000 mandiri'
        """
        clean = text.strip()
        now = datetime.now()

        # Deteksi tipe default
        tx_type = TransactionType.PENGELUARAN
        if clean.startswith("/masuk") or "pemasukan" in clean.lower() or "gaji" in clean.lower() or "dapat uang" in clean.lower():
            tx_type = TransactionType.PEMASUKAN

        # Hapus prefix command jika ada
        clean_text = re.sub(r"^/(?:tambah|keluar|masuk|catat)\s*", "", clean, flags=re.IGNORECASE).strip()

        # Ekstraksi nominal
        amount: Optional[float] = None
        # Cari pola angka atau rupiah dengan word boundary
        amount_match = re.search(r"(?:rp\.?\s*)?(\d+(?:[.,]\d+)?\s*(?:rb|ribu|k|jt|juta)\b|\d{4,})", clean_text, re.IGNORECASE)
        if amount_match:
            parsed = parse_rupiah_string(amount_match.group(0))
            if parsed and parsed > 0:
                amount = parsed
                # Hapus bagian nominal dari teks untuk menyisakan deskripsi
                clean_text = clean_text[:amount_match.start()] + clean_text[amount_match.end():]

        if not amount:
            return None

        # Deteksi sumber dana
        lower = clean.lower()
        source = TransactionSource.MANUAL.value
        if "gopay" in lower:
            source = TransactionSource.GOPAY.value
        elif "livin" in lower or "mandiri" in lower:
            source = TransactionSource.LIVIN.value
        elif "bca" in lower:
            source = TransactionSource.BCA.value
        elif "qris" in lower:
            source = TransactionSource.QRIS.value
        elif "ovo" in lower:
            source = TransactionSource.OVO.value
        elif "dana" in lower:
            source = TransactionSource.DANA.value
        elif "shopee" in lower or "spay" in lower:
            source = TransactionSource.SHOPEEPAY.value
        elif "cash" in lower or "tunai" in lower:
            source = TransactionSource.CASH.value

        # Bersihkan deskripsi
        desc = re.sub(r"[()\[\]]", " ", clean_text)
        desc = re.sub(r"\b(?:gopay|livin|mandiri|bca|ovo|dana|shopeepay|spay|qris|cash|tunai|pake|pakai|via)\b", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\s+", " ", desc).strip()

        if not desc:
            desc = "Pengeluaran" if tx_type == TransactionType.PENGELUARAN else "Pemasukan"

        category = guess_category(desc, tx_type)

        return Transaction(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M:%S"),
            type=tx_type,
            amount=amount,
            category=category,
            source=source,
            description=desc,
            input_via="MANUAL",
            status="TERCATAT",
        )


# Singleton instance
engine = FinanceEngine()
