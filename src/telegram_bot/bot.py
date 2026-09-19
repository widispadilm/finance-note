"""Inisialisasi aplikasi dan dispatcher Telegram Bot."""

from __future__ import annotations

import logging
from typing import Optional

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from src.config import settings
from src.core.engine import engine
from src.telegram_bot.handlers import (
    callback_query_handler,
    document_handler,
    help_command,
    photo_handler,
    rekap_command,
    riwayat_command,
    saldo_command,
    sheet_command,
    start_command,
    text_handler,
)

logger = logging.getLogger(__name__)


def create_bot_app() -> Optional[Application]:
    """Membuat dan mengonfigurasi aplikasi python-telegram-bot."""
    if not settings.is_telegram_configured:
        logger.warning("TELEGRAM_BOT_TOKEN belum disetel di .env. Bot Telegram dinonaktifkan.")
        return None

    app = Application.builder().token(settings.telegram_bot_token).build()

    # Daftarkan referensi bot ke engine untuk notifikasi proaktif
    engine.set_telegram_bot(app.bot)

    # 1. Command Handlers
    app.add_handler(CommandHandler(["start"], start_command))
    app.add_handler(CommandHandler(["help"], help_command))
    app.add_handler(CommandHandler(["saldo", "summary"], saldo_command))
    app.add_handler(CommandHandler(["rekap", "bulan_ini"], rekap_command))
    app.add_handler(CommandHandler(["riwayat", "recent"], riwayat_command))
    app.add_handler(CommandHandler(["sheet", "sheets"], sheet_command))
    app.add_handler(CommandHandler(["keluar", "masuk", "tambah", "catat"], text_handler))

    # 2. Photo & Document Handler (Screenshot OCR)
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.IMAGE, document_handler))

    # 3. Callback Query Handler (Inline Keyboard)
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # 4. Text Handler (Manual / Bahasa Alami)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    return app
