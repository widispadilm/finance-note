"""Manajemen database SQLite lokal untuk deduplikasi dan status transaksi."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import settings
from src.models import MonthlySummary, Transaction, TransactionType


class Database:
    """Database SQLite untuk menyimpan riwayat transaksi & deduplikasi."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        if db_path is None:
            self.db_path = settings.resolved_database_path
        else:
            self.db_path = Path(db_path)

        # Pastikan direktori database ada
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Inisialisasi tabel database jika belum ada."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Tabel email yang sudah diproses agar tidak ada email ganda
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_emails (
                    message_id TEXT PRIMARY KEY,
                    subject TEXT,
                    sender TEXT,
                    date_received TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Tabel riwayat transaksi lokal
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    reference_id TEXT,
                    timestamp TIMESTAMP,
                    date TEXT,
                    time TEXT,
                    type TEXT,
                    amount REAL,
                    category TEXT,
                    source TEXT,
                    description TEXT,
                    input_via TEXT,
                    status TEXT,
                    raw_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Index untuk pencarian referensi cepat
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_transactions_ref
                ON transactions(reference_id, amount, date)
                """
            )

            # Tabel aksi tertunda (pending confirmation Telegram)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_actions (
                    action_id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    transaction_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.commit()

    # --- Deduplikasi Email ---

    def is_email_processed(self, message_id: str) -> bool:
        """Cek apakah Message-ID email ini sudah pernah diproses."""
        if not message_id:
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM processed_emails WHERE message_id = ?",
                (message_id,),
            )
            return cursor.fetchone() is not None

    def mark_email_processed(
        self,
        message_id: str,
        subject: str = "",
        sender: str = "",
        date_str: str = "",
    ) -> None:
        """Catat bahwa Message-ID email ini telah berhasil diproses."""
        if not message_id:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO processed_emails
                (message_id, subject, sender, date_received, processed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, subject, sender, date_str, datetime.now().isoformat()),
            )
            conn.commit()

    # --- Deduplikasi & Penyimpanan Transaksi ---

    def is_transaction_duplicate(
        self,
        reference_id: str,
        amount: float,
        date: str,
    ) -> bool:
        """Cek apakah transaksi yang sama persis sudah tercatat sebelumnya."""
        if reference_id and reference_id.strip():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM transactions WHERE reference_id = ?",
                    (reference_id.strip(),),
                )
                if cursor.fetchone() is not None:
                    return True

        # Jika tidak ada referensi spesifik, cek kombinasi nominal dan tanggal serta jam dalam jendela waktu
        return False

    def save_transaction(self, tx: Transaction) -> None:
        """Simpan transaksi ke database lokal."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO transactions
                (id, reference_id, timestamp, date, time, type, amount, category, source, description, input_via, status, raw_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx.id,
                    tx.reference_id,
                    tx.timestamp.isoformat(),
                    tx.date,
                    tx.time,
                    tx.type.value,
                    tx.amount,
                    tx.category,
                    tx.source,
                    tx.description,
                    tx.input_via,
                    tx.status,
                    tx.raw_text,
                ),
            )
            conn.commit()

    def update_transaction_category(self, tx_id: str, new_category: str) -> bool:
        """Perbarui kategori transaksi di database lokal."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE transactions SET category = ? WHERE id = ?",
                (new_category, tx_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_transaction(self, tx_id: str) -> Optional[Transaction]:
        """Ambil transaksi berdasarkan ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_transaction(row)

    def get_recent_transactions(self, limit: int = 10) -> list[Transaction]:
        """Ambil daftar transaksi terbaru."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
            return [self._row_to_transaction(r) for r in rows]

    def _row_to_transaction(self, row: sqlite3.Row) -> Transaction:
        """Konversi row SQLite ke objek Transaction."""
        raw_ts = row["timestamp"]
        try:
            ts = datetime.fromisoformat(raw_ts)
        except Exception:
            ts = datetime.now()

        return Transaction(
            id=row["id"],
            timestamp=ts,
            date=row["date"] or ts.strftime("%Y-%m-%d"),
            time=row["time"] or ts.strftime("%H:%M:%S"),
            type=TransactionType(row["type"]),
            amount=float(row["amount"]),
            category=row["category"] or "Lainnya",
            source=row["source"] or "Lainnya",
            description=row["description"] or "",
            reference_id=row["reference_id"] or "",
            status=row["status"] or "TERCATAT",
            input_via=row["input_via"] or "MANUAL",
            raw_text=row["raw_text"],
        )

    # --- Pending Actions (Telegram Konfirmasi) ---

    def save_pending_action(self, action_id: str, user_id: int, tx: Transaction) -> None:
        """Simpan transaksi yang menunggu konfirmasi pengguna."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO pending_actions
                (action_id, user_id, transaction_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (action_id, user_id, tx.model_dump_json(), datetime.now().isoformat()),
            )
            conn.commit()

    def get_pending_action(self, action_id: str) -> Optional[Transaction]:
        """Ambil transaksi yang masih tertunda."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT transaction_json FROM pending_actions WHERE action_id = ?",
                (action_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row["transaction_json"])
            return Transaction(**data)

    def delete_pending_action(self, action_id: str) -> None:
        """Hapus aksi tertunda setelah selesai dieksekusi atau dibatalkan."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_actions WHERE action_id = ?", (action_id,))
            conn.commit()

    # --- Statistik Arus Kas Bulanan ---

    def get_monthly_summary(self, year: int, month: int) -> MonthlySummary:
        """Hitung rekapitulasi arus kas dari database lokal untuk bulan tertentu."""
        month_str = f"{year:04d}-{month:02d}"
        summary = MonthlySummary(year=year, month=month)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Total pemasukan & pengeluaran
            cursor.execute(
                """
                SELECT
                    type,
                    SUM(amount) as total,
                    COUNT(*) as count
                FROM transactions
                WHERE date LIKE ? AND status != 'DIBATALKAN'
                GROUP BY type
                """,
                (f"{month_str}%",),
            )

            total_count = 0
            for row in cursor.fetchall():
                t_type = row["type"]
                total = float(row["total"] or 0)
                count = int(row["count"] or 0)
                total_count += count

                if t_type == TransactionType.PEMASUKAN.value:
                    summary.total_income = total
                elif t_type == TransactionType.PENGELUARAN.value:
                    summary.total_expense = total

            summary.transaction_count = total_count
            summary.net_cashflow = summary.total_income - summary.total_expense

            # 2. Rincian pengeluaran per kategori
            cursor.execute(
                """
                SELECT category, SUM(amount) as cat_total
                FROM transactions
                WHERE date LIKE ? AND type = ? AND status != 'DIBATALKAN'
                GROUP BY category
                ORDER BY cat_total DESC
                """,
                (f"{month_str}%", TransactionType.PENGELUARAN.value),
            )
            for row in cursor.fetchall():
                summary.expenses_by_category[row["category"]] = float(row["cat_total"] or 0)

            # 3. Rincian pengeluaran per sumber dana
            cursor.execute(
                """
                SELECT source, SUM(amount) as src_total
                FROM transactions
                WHERE date LIKE ? AND type = ? AND status != 'DIBATALKAN'
                GROUP BY source
                ORDER BY src_total DESC
                """,
                (f"{month_str}%", TransactionType.PENGELUARAN.value),
            )
            for row in cursor.fetchall():
                summary.expenses_by_source[row["source"]] = float(row["src_total"] or 0)

        return summary


# Singleton instance
db = Database()
