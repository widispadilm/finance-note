"""Unit test untuk parsing input teks manual dan siklus engine."""

import pytest
from src.core.engine import FinanceEngine
from src.database import Database
from src.models import TransactionSource, TransactionType
from src.ocr.mock_engine import MockOcrEngine


def test_parse_manual_text_expense():
    eng = FinanceEngine()

    # Format perintah /keluar
    tx1 = eng.parse_manual_text("/keluar 35000 Kopi Kenangan (GoPay)")
    assert tx1 is not None
    assert tx1.amount == 35000.0
    assert tx1.type == TransactionType.PENGELUARAN
    assert tx1.source == TransactionSource.GOPAY.value
    assert tx1.category == "Makanan & Minuman"

    # Format bahasa alami dengan singkatan 'rb'
    tx2 = eng.parse_manual_text("makan bakso 25rb gopay")
    assert tx2 is not None
    assert tx2.amount == 25000.0
    assert tx2.type == TransactionType.PENGELUARAN
    assert tx2.source == TransactionSource.GOPAY.value

    # Format bensin
    tx3 = eng.parse_manual_text("isi bensin 50000 pertamina")
    assert tx3 is not None
    assert tx3.amount == 50000.0
    assert tx3.category == "Transportasi"


def test_parse_manual_text_income():
    eng = FinanceEngine()

    tx = eng.parse_manual_text("/masuk 7500000 Gaji Bulanan Kantor")
    assert tx is not None
    assert tx.amount == 7500000.0
    assert tx.type == TransactionType.PEMASUKAN
    assert tx.category == "Gaji"


@pytest.mark.asyncio
async def test_mock_ocr_and_screenshot_cycle(tmp_path):
    temp_db = Database(db_path=tmp_path / "eng_test.db")
    eng = FinanceEngine(ocr=MockOcrEngine())

    # Jalankan proses screenshot dummy
    dummy_bytes = b"fake-screenshot-image-content"
    tx, action_id = await eng.process_screenshot(dummy_bytes, user_id=123)

    assert tx is not None
    assert action_id != ""
    assert tx.amount > 0
    assert tx.input_via == "SCREENSHOT"

    # Konfirmasi simpan
    saved_tx = await eng.confirm_and_save_transaction(action_id)
    assert saved_tx is not None
    assert saved_tx.id == tx.id
