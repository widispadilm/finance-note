"""Parser email notifikasi transaksi dari Bank Mandiri / Livin' by Mandiri."""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Optional

from src.core.categorizer import guess_category
from src.models import (
    Transaction,
    TransactionSource,
    TransactionType,
    parse_rupiah_string,
)


def html_to_plain_text(html_content: str) -> str:
    """Mengubah dokumen HTML email menjadi teks biasa terstruktur."""
    if not html_content:
        return ""

    text = html.unescape(html_content)
    # Ganti tag break dan penutup tabel/paragraf dengan newline
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|h\d)>", "\n", text)
    text = re.sub(r"(?i)<td[^>]*>", " ", text)
    text = re.sub(r"(?i)</td>", " | ", text)
    # Hapus semua tag HTML yang tersisa
    text = re.sub(r"<[^>]+>", "", text)
    # Normalkan spasi ganda
    text = re.sub(r"[ \t]+", " ", text)
    # Normalkan baris kosong berulang
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def is_mandiri_transaction_email(subject: str, body: str, sender: str = "") -> bool:
    """Cek apakah email ini merupakan email notifikasi transaksi Bank Mandiri / Livin."""
    combined = f"{subject} {sender} {body[:500]}".lower()

    # Pastikan benar-benar berasal dari atau berkaitan dengan Bank Mandiri / Livin
    mandiri_origins = ["bankmandiri.co.id", "bank mandiri", "livin", "mandiri"]
    has_mandiri_origin = any(orig in combined for orig in mandiri_origins)
    if not has_mandiri_origin:
        return False

    # Ciri khas transaksi
    tx_indicators = [
        "debet", "debit", "kredit", "nominal", "transaksi berhasil",
        "rekening", "idr", "transfer", "pembayaran", "qris",
    ]
    has_tx = any(ind in combined for ind in tx_indicators)

    return has_tx


def parse_mandiri_email(
    subject: str,
    content: str,
    message_id: str = "",
) -> Optional[Transaction]:
    """Ekstraksi transaksi dari judul dan isi email Bank Mandiri.

    Mendukung format HTML maupun Plain Text.
    """
    text = html_to_plain_text(content) if "<" in content and ">" in content else content
    full_text = f"Subject: {subject}\n{text}"

    # 1. Deteksi Nominal Transaksi
    amount: Optional[float] = None

    amount_patterns = [
        r"\b(?:Nominal(?:\s+Transaksi)?|Jumlah(?:\s+Transaksi)?|Nilai)\b[\s:|]+(?:IDR|Rp\.?)?[\s:|]*([0-9.,]+)",
        r"(?:IDR|Rp\.?)\s*([0-9]{1,3}(?:[.,][0-9]{3})+(?:[.,][0-9]{2})?)",
        r"\b(?:Debet|Kredit|Debit)\b[\s:|]+(?:IDR|Rp\.?)?[\s:|]*([0-9.,]+)",
        r"\b(?:sebesar|total)\b[\s:|]+(?:IDR|Rp\.?)?[\s:|]*([0-9.,]+)",
    ]

    for pat in amount_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            parsed = parse_rupiah_string(match.group(1))
            if parsed and parsed > 0:
                amount = parsed
                break

    if amount is None:
        return None

    # 2. Deteksi Tipe Transaksi (Debit = Pengeluaran, Kredit = Pemasukan)
    tx_type = TransactionType.PENGELUARAN

    type_match = re.search(
        r"\b(?:Jenis Transaksi|Tipe|Kategori)\b[\s:|]+(Debet|Debit|Kredit)",
        text,
        re.IGNORECASE,
    )
    if type_match:
        val = type_match.group(1).lower()
        if "kredit" in val:
            tx_type = TransactionType.PEMASUKAN
        else:
            tx_type = TransactionType.PENGELUARAN
    else:
        lower_text = full_text.lower()
        if "kredit" in lower_text or "dana masuk" in lower_text or "transfer masuk" in lower_text:
            tx_type = TransactionType.PEMASUKAN
        elif "debet" in lower_text or "debit" in lower_text or "pembayaran" in lower_text or "transfer keluar" in lower_text:
            tx_type = TransactionType.PENGELUARAN

    # 3. Deteksi Tanggal & Waktu
    tx_date = ""
    tx_time = ""
    dt = datetime.now()

    date_patterns = [
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})\s*(\d{1,2}:\d{2}(?::\d{2})?)?",
        r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\s*(\d{1,2}:\d{2}(?::\d{2})?)?",
    ]

    for pat in date_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            raw_date = match.group(1)
            raw_time = match.group(2) or ""

            try:
                if "/" in raw_date or "-" in raw_date:
                    sep = "/" if "/" in raw_date else "-"
                    parts = [int(p) for p in raw_date.split(sep)]
                    if len(parts) == 3:
                        day, month, year = parts[0], parts[1], parts[2]
                        if day > 31 and year <= 31:
                            year, day = day, year
                        dt = dt.replace(year=year, month=month, day=day)
                        tx_date = dt.strftime("%Y-%m-%d")
            except Exception:
                pass

            if raw_time:
                tx_time = raw_time
                if len(tx_time.split(":")) == 2:
                    tx_time += ":00"
            break

    if not tx_date:
        tx_date = dt.strftime("%Y-%m-%d")
    if not tx_time:
        tx_time = dt.strftime("%H:%M:%S")

    # 4. Deteksi Keterangan / Merchant / Penerima / Rekening Tujuan
    description = ""
    desc_patterns = [
        # Gunakan \b agar tidak cocok dengan kata 'pemberitahuan'
        r"\b(?:Keterangan|Berita|Uraian|Deskripsi)\b[\s:|]+([^\n\r|]+)",
        r"\b(?:Merchant|Penerima|Tujuan|Ke Rekening|Kepada)\b[\s:|]+([^\n\r|]+)",
        r"\b(?:Pembayaran Di|Pembelian Di|Transaksi Di)\b[\s:|]+([^\n\r|]+)",
    ]

    for pat in desc_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            # Hindari mengambil string kosong atau kata kunci palsu
            if len(candidate) > 2 and candidate.lower() not in ["transaksi berhasil", "debet", "kredit", "rekening mandiri"]:
                description = candidate
                break

    if not description:
        if "qris" in full_text.lower():
            description = "Transaksi QRIS Livin"
        else:
            description = "Transaksi Livin Mandiri"

    description = description.replace("|", "").strip()

    # 5. Deteksi Nomor Referensi
    reference_id = ""
    ref_match = re.search(
        r"\b(?:No\.?\s*Referensi|Nomor\s*Referensi|ID\s*Transaksi|No\.?\s*Ref|Ref(?:erence)?\s*(?:No|Number)?)\b[\s:|]+([A-Za-z0-9_-]+)",
        text,
        re.IGNORECASE,
    )
    if ref_match:
        reference_id = ref_match.group(1).strip()
    elif message_id:
        reference_id = f"EMAIL-{abs(hash(message_id)) % 100000000}"

    # 6. Auto-kategorisasi
    category = guess_category(description, tx_type)

    # 7. Sumber dana
    source = TransactionSource.LIVIN.value
    if "qris" in description.lower() or "qris" in full_text.lower():
        source = f"{TransactionSource.LIVIN.value} (QRIS)"

    return Transaction(
        date=tx_date,
        time=tx_time,
        type=tx_type,
        amount=amount,
        category=category,
        source=source,
        description=description,
        reference_id=reference_id,
        input_via="EMAIL",
        status="TERCATAT",
        raw_text=full_text[:500],
    )
