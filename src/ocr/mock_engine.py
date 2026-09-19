"""Mock OCR Engine untuk pengujian unit dan simulasi alur kerja."""

from __future__ import annotations

import random
from datetime import datetime
from typing import Optional

from src.models import Transaction, TransactionSource, TransactionType
from src.ocr.base import BaseOcrEngine


class MockOcrEngine(BaseOcrEngine):
    """Engine OCR simulasi untuk pengujian tanpa memanggil Google Gemini API."""

    def __init__(self, preset_transaction: Optional[Transaction] = None) -> None:
        self.preset_transaction = preset_transaction

    async def extract_transaction(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> Optional[Transaction]:
        """Menghasilkan transaksi GoPay simulasi realistis."""
        if self.preset_transaction:
            return self.preset_transaction

        # Contoh acak transaksi GoPay yang realistis
        samples = [
            {
                "amount": 28000.0,
                "merchant": "Kopi Kenangan - Mall Ciputra",
                "category": "Makanan & Minuman",
                "source": TransactionSource.GOPAY.value,
            },
            {
                "amount": 45000.0,
                "merchant": "Gojek GoRide Menuju Kantor",
                "category": "Transportasi",
                "source": TransactionSource.GOPAY.value,
            },
            {
                "amount": 85000.0,
                "merchant": "Super Indo Swalayan",
                "category": "Belanja",
                "source": "GoPay (QRIS)",
            },
        ]
        chosen = random.choice(samples)
        now = datetime.now()
        ref = f"GP-{now.strftime('%Y%m%d%H%M')}-{random.randint(1000, 9999)}"

        return Transaction(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M:%S"),
            type=TransactionType.PENGELUARAN,
            amount=chosen["amount"],
            category=chosen["category"],
            source=chosen["source"],
            description=chosen["merchant"],
            reference_id=ref,
            input_via="SCREENSHOT",
            status="TERCATAT",
            raw_text=f"Simulasi OCR {chosen['source']}: {chosen['merchant']} Rp {chosen['amount']}",
        )
