"""Implementasi Vision AI berbasis Google Gemini untuk membaca screenshot transaksi."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional

from google import genai
from google.genai import types

from src.config import settings
from src.core.categorizer import guess_category
from src.models import (
    DEFAULT_EXPENSE_CATEGORIES,
    DEFAULT_INCOME_CATEGORIES,
    Transaction,
    TransactionSource,
    TransactionType,
)
from src.ocr.base import BaseOcrEngine

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = f"""
Anda adalah sistem cerdas pembaca bukti transaksi dan struk pembayaran Indonesia (khususnya GoPay, Livin by Mandiri, BCA, OVO, ShopeePay, DANA, QRIS, dan struk belanja Indomaret/Alfamart).

Tugas Anda:
Analisis gambar tangkapan layar (screenshot) bukti pembayaran atau mutasi ini, lalu ekstrak informasinya ke dalam format JSON murni tanpa pembuka/penutup markdown lainnya.

Daftar Kategori Pengeluaran Acuan:
{json.dumps(DEFAULT_EXPENSE_CATEGORIES, ensure_ascii=False)}

Daftar Kategori Pemasukan Acuan:
{json.dumps(DEFAULT_INCOME_CATEGORIES, ensure_ascii=False)}

Skema JSON yang WAJIB dihasilkan:
{{
  "amount": <angka nominal murni dalam rupiah tanpa titik/koma, contoh: 35000>,
  "type": <"PENGELUARAN" atau "PEMASUKAN">,
  "source": <"GoPay", "Livin' Mandiri", "QRIS", "BCA", "OVO", "ShopeePay", "DANA", atau nama bank/dompet lainnya>,
  "category": <salah satu kategori yang paling cocok dari daftar di atas>,
  "merchant": <nama toko, penerima, merchant, atau tujuan transaksi, contoh: "Kopi Kenangan" atau "PLN Postpaid">,
  "date": <tanggal transaksi format "YYYY-MM-DD", jika tahun tidak tertera gunakan tahun saat ini>,
  "time": <jam transaksi format "HH:MM:SS" atau "HH:MM", contoh: "14:30:00">,
  "reference_id": <nomor referensi, ID transaksi, atau kode unik struk jika ada>,
  "raw_summary": <ringkasan singkat transaksi satu kalimat, contoh: "Pembayaran GoPay ke Kopi Kenangan Rp 35.000">
}}

Aturan Tambahan:
1. Jika bukti menunjukkan pembayaran ke merchant, pembelian pulsa, transfer uang keluar, pesanan makanan (GoFood/GrabFood), atau belanja, tipe adalah "PENGELUARAN".
2. Jika bukti menunjukkan top up berhasil, transfer uang masuk diterima, cashback, atau pengembalian dana, tipe adalah "PEMASUKAN".
3. Pastikan nominal "amount" adalah total akhir yang dibayarkan.
4. Output HANYA JSON. Jangan berikan kata pembuka atau penjelasan di luar JSON.
"""


class GeminiVisionEngine(BaseOcrEngine):
    """Engine OCR menggunakan Google Gemini 2.0 / 1.5 Flash."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        self.api_key = api_key or settings.gemini_api_key
        self.model_name = model or settings.gemini_model
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY belum disetel pada konfigurasi .env")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _call_gemini_sync(self, image_bytes: bytes, mime_type: str) -> str:
        """Panggilan sinkron ke Gemini API."""
        client = self._get_client()
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        response = client.models.generate_content(
            model=self.model_name,
            contents=[image_part, EXTRACTION_PROMPT],
        )
        return response.text or ""

    async def extract_transaction(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> Optional[Transaction]:
        """Ekstraksi asinkron data transaksi dari gambar screenshot menggunakan Gemini."""
        if not settings.is_gemini_configured and not self.api_key:
            logger.warning("Gemini API key tidak tersedia untuk ekstraksi screenshot.")
            return None

        try:
            # Jalankan panggilan API di thread pool agar tidak memblokir async loop
            raw_output = await asyncio.to_thread(self._call_gemini_sync, image_bytes, mime_type)

            # Bersihkan blok markdown ```json ... ``` jika ada
            clean_json = raw_output.strip()
            if clean_json.startswith("```"):
                clean_json = re.sub(r"^```(?:json)?\s*", "", clean_json)
                clean_json = re.sub(r"\s*```$", "", clean_json)

            data = json.loads(clean_json)

            # Parsing fields
            amount = float(data.get("amount") or 0)
            if amount <= 0:
                logger.warning("Gemini tidak menemukan nominal transaksi valid.")
                return None

            raw_type = str(data.get("type", "PENGELUARAN")).upper()
            tx_type = (
                TransactionType.PEMASUKAN
                if "PEMASUKAN" in raw_type or "INCOME" in raw_type
                else TransactionType.PENGELUARAN
            )

            merchant = str(data.get("merchant") or "").strip()
            category = str(data.get("category") or "").strip()
            if not category or category == "Lainnya":
                category = guess_category(merchant, tx_type)

            source = str(data.get("source") or TransactionSource.GOPAY.value).strip()
            ref_id = str(data.get("reference_id") or "").strip()

            date_str = str(data.get("date") or "").strip()
            time_str = str(data.get("time") or "").strip()
            now = datetime.now()

            if not date_str or len(date_str) < 8:
                date_str = now.strftime("%Y-%m-%d")

            if not time_str:
                time_str = now.strftime("%H:%M:%S")
            elif len(time_str.split(":")) == 2:
                time_str += ":00"

            return Transaction(
                date=date_str,
                time=time_str,
                type=tx_type,
                amount=amount,
                category=category,
                source=source,
                description=merchant or f"Transaksi {source}",
                reference_id=ref_id,
                input_via="SCREENSHOT",
                status="TERCATAT",
                raw_text=data.get("raw_summary", ""),
            )

        except Exception as e:
            logger.error(f"Gagal melakukan ekstraksi screenshot via Gemini: {e}", exc_info=True)
            return None
