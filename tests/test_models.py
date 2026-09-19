"""Unit test untuk model data dan helper rupiah."""

from datetime import datetime
from src.models import (
    MonthlySummary,
    Transaction,
    TransactionSource,
    TransactionType,
    format_rupiah,
    parse_rupiah_string,
)


def test_format_rupiah():
    assert format_rupiah(50000) == "Rp 50.000"
    assert format_rupiah(1250000) == "Rp 1.250.000"
    assert format_rupiah(0) == "Rp 0"
    assert format_rupiah(75000.75) == "Rp 75.001"


def test_parse_rupiah_string():
    assert parse_rupiah_string("Rp 50.000,00") == 50000.0
    assert parse_rupiah_string("Rp. 75.000") == 75000.0
    assert parse_rupiah_string("25000") == 25000.0
    assert parse_rupiah_string("35rb") == 35000.0
    assert parse_rupiah_string("50k") == 50000.0
    assert parse_rupiah_string("1.5jt") == 1500000.0
    assert parse_rupiah_string("2,5 juta") == 2500000.0
    assert parse_rupiah_string("IDR 120.000,00") == 120000.0
    assert parse_rupiah_string("") is None


def test_transaction_model():
    tx = Transaction(
        amount=45000.0,
        type=TransactionType.PENGELUARAN,
        category="Makanan & Minuman",
        source=TransactionSource.GOPAY.value,
        description="Kopi Kenangan",
        reference_id="REF12345",
    )

    assert tx.amount == 45000.0
    assert tx.formatted_amount == "Rp 45.000"
    assert tx.type == TransactionType.PENGELUARAN
    assert tx.date != ""
    assert tx.time != ""

    sheet_row = tx.to_sheet_row()
    assert len(sheet_row) == 12
    assert sheet_row[0] == tx.id
    assert sheet_row[4] == "PENGELUARAN"
    assert sheet_row[5] == "Makanan & Minuman"
    assert sheet_row[6] == 45000.0
    assert sheet_row[7] == TransactionSource.GOPAY.value
    assert sheet_row[8] == "Kopi Kenangan"


def test_monthly_summary_model():
    summary = MonthlySummary(
        year=2026,
        month=9,
        total_income=10000000.0,
        total_expense=3500000.0,
        net_cashflow=6500000.0,
        transaction_count=15,
    )

    assert summary.formatted_income == "Rp 10.000.000"
    assert summary.formatted_expense == "Rp 3.500.000"
    assert summary.formatted_net == "+Rp 6.500.000"
