"""Unit test untuk modul pengkategorian transaksi otomatis."""

from src.core.categorizer import guess_category
from src.models import TransactionType


def test_guess_category_expenses():
    # Makanan & Minuman
    assert guess_category("Kopi Kenangan Senayan", TransactionType.PENGELUARAN) == "Makanan & Minuman"
    assert guess_category("Makan Siang Nasi Padang", TransactionType.PENGELUARAN) == "Makanan & Minuman"
    assert guess_category("Pesanan GoFood McDonald", TransactionType.PENGELUARAN) == "Makanan & Minuman"

    # Transportasi
    assert guess_category("Gojek GoRide ke Stasiun", TransactionType.PENGELUARAN) == "Transportasi"
    assert guess_category("Isi Pertamax SPBU Pertamina", TransactionType.PENGELUARAN) == "Transportasi"

    # Belanja
    assert guess_category("Indomaret Point", TransactionType.PENGELUARAN) == "Belanja"
    assert guess_category("Belanja Superindo", TransactionType.PENGELUARAN) == "Belanja"
    assert guess_category("Tokopedia Order", TransactionType.PENGELUARAN) == "Belanja"

    # Tagihan
    assert guess_category("Tagihan Listrik PLN", TransactionType.PENGELUARAN) == "Tagihan & Utilitas"
    assert guess_category("Langganan Indihome", TransactionType.PENGELUARAN) == "Tagihan & Utilitas"

    # Transfer & Topup
    assert guess_category("Top Up GoPay", TransactionType.PENGELUARAN) == "Transfer & Topup"
    assert guess_category("Transfer ke Rekening BCA", TransactionType.PENGELUARAN) == "Transfer & Topup"


def test_guess_category_income():
    assert guess_category("Gaji Bulanan September", TransactionType.PEMASUKAN) == "Gaji"
    assert guess_category("Payroll PT ABC", TransactionType.PEMASUKAN) == "Gaji"
    assert guess_category("Honor Project Freelance", TransactionType.PEMASUKAN) == "Freelance & Bisnis"
    assert guess_category("Cashback Pembayaran QRIS", TransactionType.PEMASUKAN) == "Hadiah & Cashback"
