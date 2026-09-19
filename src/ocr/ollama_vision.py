"""Implementasi Vision AI lokal berbasis Ollama untuk membaca screenshot transaksi offline."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from datetime import datetime
from typing import Optional

import aiohttp

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

OLLAMA_VISION_PROMPT = f"""
Analisis gambar struk atau tangkapan layar (screenshot) bukti transaksi/pembayaran ini (seperti GoPay, Livin Mandiri, QRIS, BCA, OVO, ShopeePay, DANA).
Ekstrak informasinya ke dalam format JSON dengan kunci berikut:

Kategori Pengeluaran: {json.dumps(DEFAULT_EXPENSE_CATEGORIES, ensure_ascii=False)}
Kategori Pemasukan: {json.dumps(DEFAULT_INCOME_CATEGORIES, ensure_ascii=False)}

Format JSON yang WAJIB dihasilkan:
{{
  "amount": <angka nominal bulat rupiah tanpa titik/koma, contoh: 25000>,
  "type": <"PENGELUARAN" atau "PEMASUKAN">,
  "source": <"GoPay", "Livin' Mandiri", "QRIS", "BCA", "OVO", "ShopeePay", "DANA", atau nama dompet/bank>,
  "category": <salah satu kategori yang paling cocok dari daftar di atas>,
  "merchant": <nama toko, penerima, merchant, atau tujuan pembayaran>,
  "date": <tanggal format "YYYY-MM-DD">,
  "time": <jam format "HH:MM:SS" atau "HH:MM">,
  "reference_id": <nomor referensi atau ID transaksi jika tertera>,
  "raw_summary": <ringkasan singkat>
}}
Output hanya JSON.
"""


class OllamaVisionEngine(BaseOcrEngine):
    """Engine OCR Vision lokal menggunakan Ollama (misal: llama3.2-vision, minicpm-v, llava)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model_name = model or settings.ollama_model

    async def extract_transaction(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> Optional[Transaction]:
        """Ekstraksi data transaksi menggunakan model multimodal Ollama lokal."""
        endpoint = f"{self.base_url}/api/generate"
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "model": self.model_name,
            "prompt": OLLAMA_VISION_PROMPT,
            "images": [b64_image],
            "stream": False,
            "format": "json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=120)  # Model lokal mungkin butuh waktu inferensi
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=payload) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"Ollama mengembalikan status HTTP {resp.status}: {err_text}")
                        return None

                    result = await resp.json()
                    response_text = result.get("response", "")

            # Bersihkan blok markdown jika ada
            clean_json = response_text.strip()
            if clean_json.startswith("```"):
                clean_json = re.sub(r"^```(?:json)?\s*", "", clean_json)
                clean_json = re.sub(r"\s*```$", "", clean_json)

            data = json.loads(clean_json)

            # Parsing fields
            amount = float(data.get("amount") or 0)
            if amount <= 0:
                logger.warning("Ollama Vision tidak menemukan nominal transaksi yang valid.")
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
                raw_text=data.get("raw_summary", f"Ollama {self.model_name}"),
            )

        except aiohttp.ClientConnectorError:
            logger.error(
                f"Tidak dapat terhubung ke server Ollama di {self.base_url}. "
                "Pastikan aplikasi Ollama sedang berjalan ('ollama serve')."
            )
            return None
        except Exception as e:
            logger.error(f"Gagal melakukan ekstraksi screenshot via Ollama: {e}", exc_info=True)
            return None
