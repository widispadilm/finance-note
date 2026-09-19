"""Modul aturan kategorisasi otomatis transaksi berdasarkan deskripsi dan merchant."""

from __future__ import annotations

import re
from src.models import DEFAULT_EXPENSE_CATEGORIES, DEFAULT_INCOME_CATEGORIES, TransactionType

# Kamus kata kunci untuk mencocokkan kategori pengeluaran secara cepat
EXPENSE_KEYWORD_RULES: dict[str, list[str]] = {
    "Makanan & Minuman": [
        "makan", "minum", "resto", "restaurant", "cafe", "coffee", "kopi", "warung", "warteg",
        "nasi", "bakso", "mie", "ayam", "sate", "pizza", "burger", "mcd", "kfc", "hokben",
        "starbucks", "kenangan", "janji jiwa", "fore", "chatime", "haus", "gofood", "grabfood",
        "shopeefood", "snack", "roti", "jco", "breadtalk", "dunkin", "kuliner",
    ],
    "Transportasi": [
        "gojek", "goride", "gocar", "grab", "grabride", "grabcar", "maxim", "indrive",
        "pertamina", "spbu", "bensin", "pertalite", "pertamax", "solar", "shell", "bp",
        "tol", "etoll", "e-toll", "parkir", "parking", "krl", "mrt", "lrt", "kereta", "kai",
        "bluebird", "taksi", "tiket pesawat", "garuda", "lion air", "citilink",
    ],
    "Belanja": [
        "indomaret", "alfamart", "alfamidi", "superindo", "hypermart", "transmart", "lotte",
        "tokopedia", "shopee", "tiktok shop", "lazada", "blibli", "bukalapak", "zalora",
        "uniqlo", "h&m", "zara", "miniso", "ikea", "ace hardware", "mr diy", "pasar", "belanja",
    ],
    "Tagihan & Utilitas": [
        "pln", "listrik", "token listrik", "pdam", "air", "indihome", "myrepublic", "first media",
        "biznet", "wifi", "telkom", "pulsa", "paket data", "kuota", "telkomsel", "indosat",
        "xl", "tri", "smartfren", "bpjs", "pajak", "pbb", "iuran",
    ],
    "Hiburan": [
        "netflix", "spotify", "youtube", "disney", "prime video", "steam", "playstation",
        "nintendo", "game", "topup game", "diamond", "xxi", "cinema 21", "cgv", "cinepolis",
        "bioskop", "karaoke", "konser", "rekreasi", "liburan", "hotel", "traveloka", "tiket.com",
    ],
    "Kesehatan": [
        "apotek", "apotik", "kimia farma", "k24", "century", "guardian", "watsons",
        "halodoc", "alodokter", "dokter", "klinik", "rumah sakit", "rs", "obat", "vitamin",
        "laboratorium", "tes darah", "gigi", "optik", "kacamata",
    ],
    "Pendidikan": [
        "sekolah", "kampus", "universitas", "spp", "kursus", "udemy", "coursera", "buku",
        "gramedia", "les", "bimbel", "seminar", "workshop",
    ],
    "Sedekah & Donasi": [
        "sedekah", "donasi", "kitabisa", "infaq", "zakat", "baznas", "dompet dhuafa", "masjid",
        "gereja", "amal", "panti",
    ],
    "Transfer & Topup": [
        "top up", "topup", "gopay", "ovo", "dana", "shopeepay", "linkaja", "transfer ke",
        "trsf ke", "antar bank", "kirim uang",
    ],
    "Investasi": [
        "bibit", "ajaib", "stockbit", "bareksa", "pluang", "toko crypto", "indodax",
        "reksadana", "saham", "deposito", "emas", "logam mulia",
    ],
}

INCOME_KEYWORD_RULES: dict[str, list[str]] = {
    "Gaji": ["gaji", "salary", "payroll", "upah", "thr"],
    "Freelance & Bisnis": ["honor", "fee", "proyek", "project", "invoicing", "klien", "penjualan"],
    "Transfer Masuk": ["transfer masuk", "trsf masuk", "terima uang", "kiriman", "dari"],
    "Investasi & Bunga": ["dividen", "bunga", "yield", "capital gain", "profit"],
    "Hadiah & Cashback": ["cashback", "reward", "hadiah", "bonus", "promo"],
}


def guess_category(
    description: str,
    tx_type: TransactionType = TransactionType.PENGELUARAN,
) -> str:
    """Menebak kategori pengeluaran atau pemasukan secara cerdas berdasarkan teks deskripsi."""
    if not description:
        return "Lainnya"

    text = description.lower()

    if tx_type == TransactionType.PENGELUARAN:
        for category, keywords in EXPENSE_KEYWORD_RULES.items():
            for kw in keywords:
                # Cek batas kata agar tidak salah tangkap substring acak
                if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE) or kw in text:
                    return category
        return "Lainnya"

    else:
        for category, keywords in INCOME_KEYWORD_RULES.items():
            for kw in keywords:
                if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE) or kw in text:
                    return category
        return "Lainnya"
