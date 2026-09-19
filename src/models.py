"""Data models untuk transaksi keuangan."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    """Tipe transaksi: Pengeluaran atau Pemasukan."""
    PENGELUARAN = "PENGELUARAN"
    PEMASUKAN = "PEMASUKAN"


class TransactionSource(str, Enum):
    """Sumber transaksi."""
    LIVIN = "Livin' Mandiri"
    GOPAY = "GoPay"
    QRIS = "QRIS"
    BCA = "BCA"
    OVO = "OVO"
    SHOPEEPAY = "ShopeePay"
    DANA = "DANA"
    CASH = "Tunai"
    MANUAL = "Manual"
    LAINNYA = "Lainnya"


DEFAULT_EXPENSE_CATEGORIES = [
    "Makanan & Minuman",
    "Transportasi",
    "Belanja",
    "Tagihan & Utilitas",
    "Hiburan",
    "Kesehatan",
    "Pendidikan",
    "Sedekah & Donasi",
    "Transfer & Topup",
    "Investasi",
    "Lainnya",
]

DEFAULT_INCOME_CATEGORIES = [
    "Gaji",
    "Freelance & Bisnis",
    "Transfer Masuk",
    "Investasi & Bunga",
    "Hadiah & Cashback",
    "Lainnya",
]


def format_rupiah(amount: float | int) -> str:
    """Format angka nominal ke representasi mata uang Rupiah Indonesia.

    Contoh: 50000 -> 'Rp 50.000'
    """
    try:
        val = int(round(float(amount)))
        # Format dengan separator ribuan titik
        formatted = f"{val:,}".replace(",", ".")
        return f"Rp {formatted}"
    except (ValueError, TypeError):
        return f"Rp {amount}"


def parse_rupiah_string(text: str) -> Optional[float]:
    """Parse string berformat rupiah atau angka ke float.

    Contoh: 'Rp 50.000,00' -> 50000.0, '25.000' -> 25000.0, '35rb' -> 35000.0
    """
    if not text:
        return None

    clean = text.strip().lower()

    # Tangani singkatan bahasa gaul Indonesia seperti 'rb' / 'k' / 'jt' dengan word boundary
    rb_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:rb|ribu)\b", clean)
    if rb_match:
        val = float(rb_match.group(1).replace(",", "."))
        return val * 1000

    k_match = re.search(r"(\d+(?:[.,]\d+)?)\s*k\b", clean)
    if k_match:
        val = float(k_match.group(1).replace(",", "."))
        return val * 1000

    jt_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:jt|juta)\b", clean)
    if jt_match:
        val = float(jt_match.group(1).replace(",", "."))
        return val * 1000000

    # Hapus prefix non-angka seperti 'rp', 'idr', spasi
    clean = re.sub(r"[^\d,.]", "", clean)
    if not clean:
        return None

    # Pola standar Indonesia: 50.000,00 (titik ribuan, koma desimal)
    if "," in clean and "." in clean:
        if clean.rfind(",") > clean.rfind("."):
            # Format Indonesia: 50.000,00
            clean = clean.replace(".", "").replace(",", ".")
        else:
            # Format US: 50,000.00
            clean = clean.replace(",", "")
    elif "." in clean and clean.count(".") >= 1:
        parts = clean.split(".")
        # Jika bagian setelah titik adalah 3 digit (misal 50.000), ini adalah pemisah ribuan
        if len(parts[-1]) == 3 or len(parts) > 2:
            clean = clean.replace(".", "")
    elif "," in clean:
        parts = clean.split(",")
        # Jika bagian setelah koma adalah 3 digit (misal 50,000), ini adalah pemisah ribuan
        if len(parts[-1]) == 3 or len(parts) > 2:
            clean = clean.replace(",", "")
        else:
            clean = clean.replace(",", ".")

    try:
        return float(clean)
    except ValueError:
        return None


class Transaction(BaseModel):
    """Data model terpadu untuk satu transaksi keuangan."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = Field(default_factory=datetime.now)
    date: str = ""
    time: str = ""
    type: TransactionType = TransactionType.PENGELUARAN
    amount: float
    category: str = "Lainnya"
    source: str = TransactionSource.LIVIN.value
    description: str = ""
    reference_id: str = ""
    status: str = "TERCATAT"
    input_via: str = "MANUAL"  # EMAIL, SCREENSHOT, MANUAL
    raw_text: Optional[str] = None

    def model_post_init(self, __context) -> None:
        """Isi date dan time secara otomatis jika kosong."""
        if not self.date:
            self.date = self.timestamp.strftime("%Y-%m-%d")
        if not self.time:
            self.time = self.timestamp.strftime("%H:%M:%S")

    @property
    def formatted_amount(self) -> str:
        """Mengembalikan nominal dalam format 'Rp X.XXX'."""
        return format_rupiah(self.amount)

    @property
    def formatted_datetime(self) -> str:
        """Mengembalikan tanggal dan jam yang ramah dibaca."""
        return f"{self.date} {self.time}"

    def to_sheet_row(self) -> list[str | float | int]:
        """Konversi model transaksi ke baris array Google Sheets.

        Struktur kolom:
        1. ID
        2. Timestamp ISO
        3. Tanggal (YYYY-MM-DD)
        4. Jam (HH:MM:SS)
        5. Tipe (PENGELUARAN / PEMASUKAN)
        6. Kategori
        7. Nominal (Angka murni agar bisa diformat dan dirumus oleh Sheets)
        8. Sumber Dana (Livin Mandiri, GoPay, dll)
        9. Merchant / Keterangan
        10. No. Referensi
        11. Input Via
        12. Status
        """
        return [
            self.id,
            self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            self.date,
            self.time,
            self.type.value,
            self.category,
            self.amount,
            self.source,
            self.description,
            self.reference_id,
            self.input_via,
            self.status,
        ]


class MonthlySummary(BaseModel):
    """Model ringkasan arus kas bulanan."""

    year: int
    month: int
    total_income: float = 0.0
    total_expense: float = 0.0
    net_cashflow: float = 0.0
    transaction_count: int = 0
    expenses_by_category: dict[str, float] = Field(default_factory=dict)
    expenses_by_source: dict[str, float] = Field(default_factory=dict)

    @property
    def formatted_income(self) -> str:
        return format_rupiah(self.total_income)

    @property
    def formatted_expense(self) -> str:
        return format_rupiah(self.total_expense)

    @property
    def formatted_net(self) -> str:
        sign = "+" if self.net_cashflow >= 0 else "-"
        return f"{sign}{format_rupiah(abs(self.net_cashflow))}"
