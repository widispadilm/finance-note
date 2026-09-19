"""Unit test untuk parser email Bank Mandiri Livin."""

from src.email_listener.mandiri_parser import (
    is_mandiri_transaction_email,
    parse_mandiri_email,
)
from src.models import TransactionType


def test_is_mandiri_transaction_email():
    subject = "Pemberitahuan Transaksi Rekening Mandiri"
    sender = "noreply@bankmandiri.co.id"
    body = "Yth. Nasabah, transaksi debet sebesar IDR 50.000 telah berhasil."
    assert is_mandiri_transaction_email(subject, body, sender) is True

    # Email promo atau biasa non-transaksi
    non_tx_sub = "Promo Spesial Livin' POIN Bank Mandiri"
    non_tx_body = "Dapatkan diskon menarik di merchant pilihan Anda."
    assert is_mandiri_transaction_email(non_tx_sub, non_tx_body, sender) is False

    # Email dari bank lain
    bca_sub = "Notifikasi Transaksi BCA"
    assert is_mandiri_transaction_email(bca_sub, "Transaksi berhasil", "info@bca.co.id") is False


def test_parse_mandiri_qris_email():
    subject = "Pemberitahuan Transaksi Rekening Mandiri"
    body = """
    Yth. Bapak/Ibu,

    Pemberitahuan Transaksi Rekening Mandiri
    Nomor Rekening   : 137-00-****-5678
    Tanggal & Waktu  : 19/09/2026 08:30:15 WIB
    Jenis Transaksi  : Debet
    Nominal          : IDR 75.000,00
    Keterangan       : QRIS KOPI KENANGAN JAKARTA
    No. Referensi    : 2026091912345678
    Saldo Akhir      : IDR 2.450.000,00

    Terima kasih telah menggunakan layanan Bank Mandiri.
    """
    tx = parse_mandiri_email(subject, body, message_id="MSG-001")
    assert tx is not None
    assert tx.amount == 75000.0
    assert tx.type == TransactionType.PENGELUARAN
    assert tx.category == "Makanan & Minuman"
    assert "Livin" in tx.source
    assert "KOPI KENANGAN" in tx.description
    assert tx.reference_id == "2026091912345678"
    assert tx.date == "2026-09-19"
    assert tx.time == "08:30:15"


def test_parse_mandiri_transfer_keluar():
    subject = "Transaksi Berhasil Livin' by Mandiri"
    body = """
    Transaksi Berhasil
    Sumber Rekening: 1370012345678
    Penerima: Bank BCA 8830123456 a.n. AHMAD FAUZI
    Tanggal: 19/09/2026 14:15:00 WIB
    Jumlah: Rp 250.000
    Keterangan: Bayar Kas Kantor
    No Referensi: 2026091999887766
    """
    tx = parse_mandiri_email(subject, body, message_id="MSG-002")
    assert tx is not None
    assert tx.amount == 250000.0
    assert tx.type == TransactionType.PENGELUARAN
    assert tx.reference_id == "2026091999887766"


def test_parse_mandiri_kredit_masuk():
    subject = "Pemberitahuan Transaksi Rekening Mandiri"
    body = """
    Yth. Nasabah,
    Pemberitahuan Transaksi Rekening Mandiri
    Nomor Rekening   : 137-00-****-5678
    Tanggal & Waktu  : 19/09/2026 10:00:00 WIB
    Jenis Transaksi  : Kredit
    Nominal          : IDR 6.500.000,00
    Keterangan       : TRSF DARI PT KARYA MAKMUR GAJI BULANAN
    No. Referensi    : 2026091955555555
    """
    tx = parse_mandiri_email(subject, body, message_id="MSG-003")
    assert tx is not None
    assert tx.amount == 6500000.0
    assert tx.type == TransactionType.PEMASUKAN
    assert tx.category == "Gaji"
    assert tx.reference_id == "2026091955555555"


def test_parse_mandiri_html_format():
    subject = "Notifikasi Transaksi Rekening Mandiri"
    html_content = """
    <html>
      <body>
        <table border="0">
          <tr><td>Jenis Transaksi</td><td>:</td><td>Debet</td></tr>
          <tr><td>Nominal Transaksi</td><td>:</td><td>IDR 125.000,00</td></tr>
          <tr><td>Tanggal & Waktu</td><td>:</td><td>19/09/2026 12:45:00 WIB</td></tr>
          <tr><td>Keterangan</td><td>:</td><td>PEMBELIAN DI INDOMARET PLAZA</td></tr>
          <tr><td>No. Referensi</td><td>:</td><td>2026091988887777</td></tr>
        </table>
      </body>
    </html>
    """
    tx = parse_mandiri_email(subject, html_content, message_id="MSG-004")
    assert tx is not None
    assert tx.amount == 125000.0
    assert tx.type == TransactionType.PENGELUARAN
    assert tx.category == "Belanja"
    assert tx.reference_id == "2026091988887777"
