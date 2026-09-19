"""Entrypoint utama untuk menjalankan Finance Note Bot dan Email Listener secara bersamaan."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

# Pastikan output terminal Windows mendukung UTF-8 dan emoji
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console

from src.config import settings
from src.core.engine import engine
from src.database import db
from src.email_listener.imap_client import EmailListener
from src.sheets.client import sheets_client
from src.telegram_bot.bot import create_bot_app

# Konfigurasi logging
logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("finance_note")
console = Console()


async def run_services() -> None:
    """Menjalankan layanan pemantau email Mandiri dan bot Telegram secara paralel."""
    console.print("\n[bold cyan]🚀 Memulai Layanan Finance Note...[/bold cyan]")

    # 1. Inisialisasi Database
    db.init_db()

    # 2. Inisialisasi Google Sheets jika kredensial sudah ada
    if sheets_client.is_configured():
        try:
            sheets_client.initialize_sheets()
            console.print(" [green]✓[/green] Google Sheets terhubung dan tab siap digunakan.")
        except Exception as e:
            console.print(f" [yellow]![/yellow] Google Sheets gagal diinisialisasi: {e}")
    else:
        console.print(" [yellow]ℹ[/yellow] Google Sheets belum dikonfigurasi. Transaksi akan disimpan di database lokal SQLite.")

    # 3. Setup Email Listener
    email_listener = EmailListener()
    stop_event = asyncio.Event()

    # Handle graceful exit on Ctrl+C (Windows & Linux compatible)
    def signal_handler():
        logger.info("Menerima sinyal terminasi. Menghentikan layanan...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)
    except NotImplementedError:
        # Pada Windows add_signal_handler mungkin tidak diimplementasikan untuk semua signal
        pass

    # 4. Setup HTTP Health Check Server (Untuk Render Web Service & Cloud Monitoring)
    from aiohttp import web

    async def health_handler(request):
        return web.json_response({
            "status": "online",
            "service": "Finance Note Bot",
            "bot": "@FinWidBot",
            "email": settings.email_imap_user,
            "sheets": "connected" if sheets_client.is_configured() else "disconnected",
        })

    http_app = web.Application()
    http_app.router.add_get("/", health_handler)
    http_app.router.add_get("/health", health_handler)
    http_runner = web.AppRunner(http_app)
    await http_runner.setup()
    http_site = web.TCPSite(http_runner, "0.0.0.0", settings.port)
    try:
        await http_site.start()
        console.print(f" [green]✓[/green] HTTP Health Check aktif di port {settings.port} (Siap untuk Render).")
    except Exception as ex:
        console.print(f" [yellow]![/yellow] Port {settings.port} tidak dapat diikat (bukan cloud environment): {ex}")

    # 5. Setup Bot Telegram
    telegram_app = create_bot_app()

    tasks = []

    # Task pemantau email
    if settings.is_email_configured:
        console.print(f" [green]✓[/green] Email Listener aktif (memeriksa setiap {settings.email_check_interval_seconds}s).")
        email_task = asyncio.create_task(
            email_listener.start_listening(
                on_transaction_found=engine.process_email_transaction,
                stop_event=stop_event,
            )
        )
        tasks.append(email_task)
    else:
        console.print(" [yellow]ℹ[/yellow] Email Mandiri IMAP belum dikonfigurasi di .env. Melewati pemantau email.")

    # Task Telegram Bot
    if telegram_app:
        console.print(" [green]✓[/green] Telegram Bot aktif. Menunggu pesan dan screenshot dari pengguna...")
        async with telegram_app:
            await telegram_app.initialize()
            await telegram_app.start()
            try:
                await telegram_app.updater.start_polling(drop_pending_updates=True)
            except Exception as ex:
                logger.error(f"Peringatan polling Telegram: {ex}")

            # Tunggu sampai stop_event menyala
            try:
                await stop_event.wait()
            except (asyncio.CancelledError, KeyboardInterrupt):
                pass
            finally:
                console.print("\n[yellow]Menghentikan Telegram Bot...[/yellow]")
                email_listener.stop()
                await http_runner.cleanup()
                try:
                    if telegram_app.updater and telegram_app.updater.running:
                        await telegram_app.updater.stop()
                except Exception:
                    pass
                await telegram_app.stop()
                await telegram_app.shutdown()
    else:
        console.print(" [yellow]ℹ[/yellow] Telegram Bot belum dikonfigurasi di .env.")
        if tasks:
            console.print("Menjalankan hanya layanan pemantau email...")
            try:
                await asyncio.gather(*tasks)
            except (asyncio.CancelledError, KeyboardInterrupt):
                pass
        else:
            console.print("\n[bold yellow]Semua kredensial (.env) masih kosong atau belum aktif.[/bold yellow]")
            console.print("Anda dapat mencoba simulasi transaksi lengkap dengan menjalankan:")
            console.print("[bold cyan]python -m src.cli simulate-flow[/bold cyan]\n")
            console.print("Atau periksa status sistem dengan:")
            console.print("[bold cyan]python -m src.cli status[/bold cyan]\n")


def main() -> None:
    """Fungsi utama launcher."""
    try:
        asyncio.run(run_services())
    except (KeyboardInterrupt, SystemExit):
        console.print("\n[green]Layanan Finance Note dihentikan dengan aman. Sampai jumpa![/green]")


if __name__ == "__main__":
    main()
