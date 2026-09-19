"""Formatter pesan dan inline keyboard untuk Telegram Bot."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.models import (
    DEFAULT_EXPENSE_CATEGORIES,
    DEFAULT_INCOME_CATEGORIES,
    MonthlySummary,
    Transaction,
    TransactionType,
    format_rupiah,
)


def format_transaction_card(
    tx: Transaction,
    title: str = "Bukti Transaksi Terdeteksi",
    is_saved: bool = False,
) -> str:
    """Format kartu informasi transaksi yang rapi dan elegan."""
    is_expense = tx.type == TransactionType.PENGELUARAN
    type_badge = "🔴 Pengeluaran" if is_expense else "🟢 Pemasukan"
    status_icon = "✅ Tercatat di Sheets" if is_saved else "⏳ Menunggu Konfirmasi"

    lines = [
        f"🧾 *{title}*",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"💸 *Tipe:* {type_badge}",
        f"💰 *Nominal:* `{tx.formatted_amount}`",
        f"🏷 *Kategori:* {tx.category}",
        f"💳 *Sumber:* {tx.source}",
        f"🏪 *Keterangan:* {tx.description or '-'}",
        f"📅 *Waktu:* {tx.formatted_datetime}",
    ]

    if tx.reference_id:
        lines.append(f"🔖 *No. Ref:* `{tx.reference_id}`")

    lines.append(f"📌 *Status:* _{status_icon}_")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def build_transaction_keyboard(action_id: str) -> InlineKeyboardMarkup:
    """Keyboard aksi untuk transaksi baru dari screenshot."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Simpan ke Sheet", callback_data=f"save:{action_id}"),
            InlineKeyboardButton("✏️ Ubah Kategori", callback_data=f"cat:{action_id}"),
        ],
        [
            InlineKeyboardButton("❌ Batalkan", callback_data=f"cancel:{action_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_saved_transaction_keyboard(tx_id: str) -> InlineKeyboardMarkup:
    """Keyboard aksi untuk transaksi yang sudah tersimpan (misal dari notifikasi Livin)."""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Ubah Kategori", callback_data=f"change_cat:{tx_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_category_grid(action_or_tx_id: str, is_expense: bool = True, prefix: str = "set_cat") -> InlineKeyboardMarkup:
    """Grid pilihan kategori untuk tombol interaktif."""
    categories = DEFAULT_EXPENSE_CATEGORIES if is_expense else DEFAULT_INCOME_CATEGORIES

    keyboard = []
    row = []
    for cat in categories:
        # Singkatkan label tombol jika terlalu panjang
        btn_text = cat.replace(" & ", "/")
        row.append(InlineKeyboardButton(btn_text, callback_data=f"{prefix}:{action_or_tx_id}:{cat}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data=f"back:{action_or_tx_id}")])
    return InlineKeyboardMarkup(keyboard)


def format_monthly_summary_card(summary: MonthlySummary) -> str:
    """Format kartu laporan arus kas dan rekap bulanan."""
    months_id = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    month_name = months_id[summary.month] if 1 <= summary.month <= 12 else str(summary.month)

    net_badge = "🟢 Positif (Surplus)" if summary.net_cashflow >= 0 else "🔴 Negatif (Defisit)"

    lines = [
        f"📊 *REKAP CASHFLOW - {month_name.upper()} {summary.year}*",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"📥 *Total Pemasukan:* `{summary.formatted_income}`",
        f"📤 *Total Pengeluaran:* `{summary.formatted_expense}`",
        f"⚖️ *Arus Kas Bersih:* `{summary.formatted_net}`",
        f"📈 *Kondisi:* {net_badge}",
        f"🔢 *Total Transaksi:* {summary.transaction_count}",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    if summary.expenses_by_category:
        lines.append("🏷 *Pengeluaran per Kategori:*")
        total_exp = summary.total_expense or 1.0
        for cat, val in summary.expenses_by_category.items():
            pct = int((val / total_exp) * 100)
            bar_len = min(10, max(1, pct // 10))
            bar = "█" * bar_len + "░" * (10 - bar_len)
            lines.append(f"• {cat}: `{format_rupiah(val)}` ({pct}%)\n  `[{bar}]`")
        lines.append("━━━━━━━━━━━━━━━━━━━━━")

    if summary.expenses_by_source:
        lines.append("💳 *Pengeluaran per Sumber Dana:*")
        for src, val in summary.expenses_by_source.items():
            lines.append(f"• {src}: `{format_rupiah(val)}`")
        lines.append("━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def format_recent_transactions_card(transactions: list[Transaction]) -> str:
    """Format daftar riwayat transaksi terakhir."""
    if not transactions:
        return "ℹ️ Belum ada transaksi yang tercatat."

    lines = [
        "📋 *5 TRANSAKSI TERAKHIR*",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    for tx in transactions:
        is_exp = tx.type == TransactionType.PENGELUARAN
        icon = "🔴" if is_exp else "🟢"
        lines.append(
            f"{icon} `{tx.formatted_amount}` | {tx.category}\n"
            f"   _{tx.description or tx.source}_ ({tx.date})\n"
            f"   ID: `{tx.id}`"
        )
        lines.append("─────────────────────")

    return "\n".join(lines)
