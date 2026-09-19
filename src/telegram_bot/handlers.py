"""Handler pesan, perintah, dan callback query untuk Telegram Bot."""

from __future__ import annotations

import io
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from src.config import settings
from src.core.engine import engine
from src.database import db
from src.sheets.client import sheets_client
from src.telegram_bot.formatters import (
    build_category_grid,
    build_saved_transaction_keyboard,
    build_transaction_keyboard,
    format_monthly_summary_card,
    format_recent_transactions_card,
    format_transaction_card,
)

logger = logging.getLogger(__name__)


def check_auth(update: Update) -> bool:
    """Verifikasi apakah pengguna diizinkan menggunakan bot."""
    if not update.effective_user:
        return False
    user_id = update.effective_user.id
    return settings.is_user_allowed(user_id)


# --- Perintah Dasar ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler perintah /start."""
    if not check_auth(update):
        await update.message.reply_text("⛔ Anda tidak memiliki izin untuk menggunakan bot ini.")
        return

    welcome_msg = (
        "👋 *Halo! Selamat datang di Finance Note Bot.*\n\n"
        "Saya siap membantu mencatat pemasukan dan pengeluaran Anda secara otomatis dan rapi di Google Sheets.\n\n"
        "✨ *Fitur Unggulan:*\n"
        "1. 📸 *Kirim Screenshot Bukti Transaksi:* Kirimkan foto resi GoPay, Livin, QRIS, dll. Saya akan membacanya via OCR AI!\n"
        "2. 📬 *Notifikasi Realtime Livin Mandiri:* Transaksi email Bank Mandiri langsung tercatat dan dilaporkan di sini.\n"
        "3. 💬 *Catat Cepat Bahasa Alami:* Cukup ketik _'makan siang 35rb gopay'_ atau _'/keluar 50000 bensin'_.\n"
        "4. 📊 *Laporan Cashflow:* Pantau saldo & grafik pengeluaran bulanan.\n\n"
        "💡 *Daftar Perintah:*\n"
        "• /saldo atau /summary - Cek total pemasukan, pengeluaran & net cashflow\n"
        "• /rekap - Rincian pengeluaran per kategori\n"
        "• /riwayat - 5 transaksi terakhir\n"
        "• /sheet - Buka tautan Google Sheets Anda\n"
        "• /help - Panduan lengkap"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler perintah /help."""
    if not check_auth(update):
        return

    help_msg = (
        "📖 *PANDUAN LENGKAP FINANCE NOTE BOT*\n\n"
        "1️⃣ *Input via Screenshot:*\n"
        "Kirim foto atau screenshot struk/mutasi pembayaran (GoPay, QRIS, Livin, OVO, dll). Sistem akan membaca nominal, tanggal, dan merchant secara otomatis.\n\n"
        "2️⃣ *Input Manual Cepat:*\n"
        "• `/keluar 25000 Kopi Kenangan (GoPay)`\n"
        "• `/masuk 5000000 Gaji Bulanan`\n"
        "• Atau langsung ketik teks: _'beli pulsa 50rb livin'_\n\n"
        "3️⃣ *Perintah Laporan:*\n"
        "• `/saldo` - Ringkasan kas bulan ini\n"
        "• `/rekap` - Breakdown per kategori\n"
        "• `/riwayat` - Daftar transaksi terakhir\n"
        "• `/sheet` - Link ke spreadsheet Google Sheets"
    )
    await update.message.reply_text(help_msg, parse_mode="Markdown")


async def saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler perintah /saldo dan /summary."""
    if not check_auth(update):
        return

    now = datetime.now()
    summary = sheets_client.get_monthly_summary(now.year, now.month)
    text = format_monthly_summary_card(summary)
    await update.message.reply_text(text, parse_mode="Markdown")


async def rekap_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler perintah /rekap."""
    await saldo_command(update, context)


async def riwayat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler perintah /riwayat."""
    if not check_auth(update):
        return

    transactions = db.get_recent_transactions(limit=5)
    text = format_recent_transactions_card(transactions)
    await update.message.reply_text(text, parse_mode="Markdown")


async def sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler perintah /sheet untuk membuka spreadsheet."""
    if not check_auth(update):
        return

    sheet_id = settings.google_spreadsheet_id
    if sheet_id and sheet_id != "your_google_spreadsheet_id_here":
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        await update.message.reply_text(f"📊 *Tautan Google Sheets Anda:*\n[Buka Google Sheets]({url})", parse_mode="Markdown")
    else:
        await update.message.reply_text("ℹ️ ID Google Sheets belum dikonfigurasi di file `.env`.")


# --- Handler Foto & Dokumen (Screenshot Bukti Pembayaran) ---

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler foto screenshot bukti transaksi."""
    if not check_auth(update):
        return

    message = update.message
    photos = message.photo
    if not photos:
        return

    # Ambil foto resolusi tertinggi
    photo = photos[-1]
    user_id = update.effective_user.id

    status_msg = await message.reply_text("🔍 *Memindai bukti transaksi via OCR AI...*", parse_mode="Markdown")

    try:
        file = await photo.get_file()
        photo_bytes = await file.download_as_bytearray()

        tx, action_or_status = await engine.process_screenshot(bytes(photo_bytes), user_id)
        if not tx:
            await status_msg.edit_text(f"❌ {action_or_status}")
            return

        if action_or_status == "saved":
            # Auto-saved
            card_text = format_transaction_card(tx, title="Bukti Transaksi Tersimpan", is_saved=True)
            keyboard = build_saved_transaction_keyboard(tx.id)
            await status_msg.edit_text(card_text, parse_mode="Markdown", reply_markup=keyboard)
        elif action_or_status == "failed_sync":
            card_text = format_transaction_card(tx, title="Bukti Transaksi Dicatat (Lokal)", is_saved=False)
            card_text += "\n\n⚠️ _Catatan: Belum tersinkron ke Google Sheets. Periksa kredensial Google._"
            keyboard = build_saved_transaction_keyboard(tx.id)
            await status_msg.edit_text(card_text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            # Menunggu konfirmasi
            action_id = action_or_status
            card_text = format_transaction_card(tx, title="Bukti Transaksi Terdeteksi", is_saved=False)
            keyboard = build_transaction_keyboard(action_id)
            await status_msg.edit_text(card_text, parse_mode="Markdown", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error memproses screenshot: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Terjadi kesalahan saat memproses gambar: {str(e)[:100]}")


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler dokumen berupa gambar."""
    if not check_auth(update):
        return

    doc = update.message.document
    if not doc or not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("ℹ️ Mohon kirimkan file berupa gambar screenshot (JPG, PNG, WEBP).")
        return

    user_id = update.effective_user.id
    status_msg = await update.message.reply_text("🔍 *Memindai bukti transaksi via OCR AI...*", parse_mode="Markdown")

    try:
        file = await doc.get_file()
        file_bytes = await file.download_as_bytearray()

        tx, action_or_status = await engine.process_screenshot(
            bytes(file_bytes),
            user_id,
            mime_type=doc.mime_type,
        )
        if not tx:
            await status_msg.edit_text(f"❌ {action_or_status}")
            return

        if action_or_status == "saved":
            card_text = format_transaction_card(tx, title="Bukti Transaksi Tersimpan", is_saved=True)
            keyboard = build_saved_transaction_keyboard(tx.id)
            await status_msg.edit_text(card_text, parse_mode="Markdown", reply_markup=keyboard)
        elif action_or_status == "failed_sync":
            card_text = format_transaction_card(tx, title="Bukti Transaksi Dicatat (Lokal)", is_saved=False)
            card_text += "\n\n⚠️ _Catatan: Belum tersinkron ke Google Sheets. Periksa kredensial Google._"
            keyboard = build_saved_transaction_keyboard(tx.id)
            await status_msg.edit_text(card_text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            action_id = action_or_status
            card_text = format_transaction_card(tx, title="Bukti Transaksi Terdeteksi", is_saved=False)
            keyboard = build_transaction_keyboard(action_id)
            await status_msg.edit_text(card_text, parse_mode="Markdown", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error memproses dokumen gambar: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Terjadi kesalahan: {str(e)[:100]}")


# --- Handler Callback Query (Tombol Interaktif) ---

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler untuk tombol inline interaktif."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data
    parts = data.split(":")
    action = parts[0]

    if action == "save":
        # Simpan transaksi ke Google Sheets
        action_id = parts[1]
        tx = await engine.confirm_and_save_transaction(action_id)
        if tx:
            is_saved = (tx.status == "TERCATAT")
            title = "Transaksi Berhasil Disimpan" if is_saved else "Transaksi Dicatat (DB Lokal)"
            card_text = format_transaction_card(tx, title=title, is_saved=is_saved)
            if not is_saved:
                card_text += "\n\n⚠️ _Catatan: Belum tersinkron ke Google Sheets. Periksa kredensial Google._"
            keyboard = build_saved_transaction_keyboard(tx.id)
            await query.edit_message_text(card_text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            await query.edit_message_text("⚠️ Transaksi telah kadaluarsa atau sudah pernah disimpan.")

    elif action == "cancel":
        # Batalkan transaksi
        action_id = parts[1]
        engine.cancel_pending_transaction(action_id)
        await query.edit_message_text("❌ Transaksi dibatalkan.")

    elif action == "cat":
        # Tampilkan grid pilihan kategori untuk pending transaction
        action_id = parts[1]
        keyboard = build_category_grid(action_id, is_expense=True, prefix="set_cat")
        await query.edit_message_reply_markup(reply_markup=keyboard)

    elif action == "set_cat":
        # Pengguna memilih kategori baru untuk pending transaction
        action_id = parts[1]
        new_category = parts[2]
        tx = engine.update_pending_category(action_id, new_category)
        if tx:
            card_text = format_transaction_card(tx, title="Bukti Transaksi Terdeteksi", is_saved=False)
            keyboard = build_transaction_keyboard(action_id)
            await query.edit_message_text(card_text, parse_mode="Markdown", reply_markup=keyboard)

    elif action == "change_cat":
        # Pengguna ingin mengubah kategori transaksi yang sudah tersimpan
        tx_id = parts[1]
        keyboard = build_category_grid(tx_id, is_expense=True, prefix="update_cat")
        await query.edit_message_reply_markup(reply_markup=keyboard)

    elif action == "update_cat":
        # Perbarui kategori transaksi yang sudah tersimpan di Sheets
        tx_id = parts[1]
        new_category = parts[2]
        sheets_client.update_transaction_category(tx_id, new_category)
        tx = db.get_transaction(tx_id)
        if tx:
            card_text = format_transaction_card(tx, title="Kategori Berhasil Diperbarui", is_saved=True)
            keyboard = build_saved_transaction_keyboard(tx.id)
            await query.edit_message_text(card_text, parse_mode="Markdown", reply_markup=keyboard)

    elif action == "back":
        # Kembali ke tampilan kartu transaksi
        action_id = parts[1]
        tx = db.get_pending_action(action_id)
        if tx:
            card_text = format_transaction_card(tx, title="Bukti Transaksi Terdeteksi", is_saved=False)
            keyboard = build_transaction_keyboard(action_id)
            await query.edit_message_text(card_text, parse_mode="Markdown", reply_markup=keyboard)


# --- Handler Teks Manual & Bahasa Alami ---

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler pesan teks biasa untuk pencatatan transaksi manual atau bahasa alami."""
    if not check_auth(update):
        return

    text = update.message.text
    if not text:
        return

    tx = engine.parse_manual_text(text)
    if tx:
        # Berhasil diparsing sebagai transaksi!
        success = sheets_client.append_transaction(tx)
        if success:
            tx.status = "TERCATAT"
            db.save_transaction(tx)
            card_text = format_transaction_card(tx, title="Transaksi Manual Dicatat", is_saved=True)
        else:
            tx.status = "GAGAL_SYNC"
            db.save_transaction(tx)
            card_text = format_transaction_card(tx, title="Transaksi Manual Dicatat (DB Lokal)", is_saved=False)
            card_text += "\n\n⚠️ _Catatan: Belum tersinkron ke Google Sheets. Periksa kredensial Google di server._"
        keyboard = build_saved_transaction_keyboard(tx.id)
        await update.message.reply_text(card_text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        # Jika bukan transaksi, tampilkan panduan singkat jika mengandung kata uang/beli
        lower = text.lower()
        if any(k in lower for k in ["beli", "bayar", "transfer", "keluar", "masuk", "rp"]):
            await update.message.reply_text(
                "💡 *Format input teks belum dikenali.*\n"
                "Contoh yang benar:\n"
                "• `makan siang 25rb gopay`\n"
                "• `beli bensin 50000 mandiri`\n"
                "• `/keluar 35000 Kopi Kenangan (GoPay)`\n"
                "• `/masuk 5000000 Gaji`",
                parse_mode="Markdown",
            )
