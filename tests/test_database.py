"""Unit test untuk database SQLite lokal dan deduplikasi."""

import pytest
from src.database import Database
from src.models import Transaction, TransactionSource, TransactionType


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_finance.db"
    return Database(db_path=db_file)


def test_email_deduplication(temp_db):
    msg_id = "test-msg-123@mandiri.co.id"
    assert temp_db.is_email_processed(msg_id) is False

    temp_db.mark_email_processed(msg_id, subject="Debit Notif", sender="noreply@bankmandiri.co.id")
    assert temp_db.is_email_processed(msg_id) is True


def test_transaction_crud_and_summary(temp_db):
    tx1 = Transaction(
        amount=50000.0,
        type=TransactionType.PENGELUARAN,
        category="Makanan & Minuman",
        source=TransactionSource.GOPAY.value,
        description="Makan Siang",
        reference_id="REF-001",
        date="2026-09-19",
    )
    tx2 = Transaction(
        amount=2500000.0,
        type=TransactionType.PEMASUKAN,
        category="Freelance & Bisnis",
        source=TransactionSource.LIVIN.value,
        description="Project Website",
        reference_id="REF-002",
        date="2026-09-19",
    )

    temp_db.save_transaction(tx1)
    temp_db.save_transaction(tx2)

    # Cek duplikasi
    assert temp_db.is_transaction_duplicate("REF-001", 50000.0, "2026-09-19") is True
    assert temp_db.is_transaction_duplicate("REF-999", 50000.0, "2026-09-19") is False

    # Cek ambil transaksi
    retrieved = temp_db.get_transaction(tx1.id)
    assert retrieved is not None
    assert retrieved.amount == 50000.0

    # Cek update kategori
    temp_db.update_transaction_category(tx1.id, "Hiburan")
    updated = temp_db.get_transaction(tx1.id)
    assert updated.category == "Hiburan"

    # Cek recent
    recent = temp_db.get_recent_transactions(limit=5)
    assert len(recent) == 2

    # Cek summary
    summary = temp_db.get_monthly_summary(2026, 9)
    assert summary.total_expense == 50000.0
    assert summary.total_income == 2500000.0
    assert summary.net_cashflow == 2450000.0
    assert summary.transaction_count == 2


def test_pending_action_lifecycle(temp_db):
    action_id = "act-12345"
    user_id = 999
    tx = Transaction(
        amount=35000.0,
        type=TransactionType.PENGELUARAN,
        category="Makanan & Minuman",
        source="GoPay",
        description="Fore Coffee",
    )

    temp_db.save_pending_action(action_id, user_id, tx)
    pending_tx = temp_db.get_pending_action(action_id)
    assert pending_tx is not None
    assert pending_tx.amount == 35000.0
    assert pending_tx.description == "Fore Coffee"

    temp_db.delete_pending_action(action_id)
    assert temp_db.get_pending_action(action_id) is None
