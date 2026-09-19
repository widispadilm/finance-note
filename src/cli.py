"""CLI Tool untuk diagnostik, pengujian, dan simulasi Finance Note."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Pastikan output terminal Windows mendukung UTF-8 dan emoji
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import settings
from src.core.engine import engine
from src.database import db
from src.email_listener.imap_client import EmailListener
from src.models import (
    Transaction,
    TransactionSource,
    TransactionType,
    format_rupiah,
)
from src.ocr.gemini_vision import GeminiVisionEngine
from src.ocr.mock_engine import MockOcrEngine
from src.sheets.client import sheets_client

console = Console()


@click.group()
def cli() -> None:
    """Finance Note CLI - Otomatisasi Pencatatan Arus Kas Keuangan."""
    pass


@cli.command()
def status() -> None:
    """Cek status konfigurasi seluruh modul sistem."""
    console.print(Panel.fit("🔍 [bold cyan]Status Konfigurasi Finance Note[/bold cyan]"))

    table = Table(title="Komponen & Kredensial", show_lines=True)
    table.add_column("Komponen", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Keterangan")

    # Telegram
    if settings.is_telegram_configured:
        tg_status = "[bold green]TERHUBUNG[/bold green]"
        tg_detail = f"Token terkonfigurasi. User ID: {settings.allowed_telegram_user_ids or 'Semua'}"
    else:
        tg_status = "[bold red]BELUM AKTIF[/bold red]"
        tg_detail = "Isi TELEGRAM_BOT_TOKEN di .env"
    table.add_row("Telegram Bot", tg_status, tg_detail)

    # Google Sheets
    if settings.is_sheets_configured:
        gs_status = "[bold green]TERHUBUNG[/bold green]"
        gs_detail = f"Spreadsheet ID: {settings.google_spreadsheet_id[:10]}..."
    else:
        gs_status = "[bold yellow]PARSIAL / LOCAL[/bold yellow]"
        gs_detail = "service_account.json atau GOOGLE_SPREADSHEET_ID belum lengkap (transaksi tetap tercatat di SQLite)"
    table.add_row("Google Sheets", gs_status, gs_detail)

    # Email Mandiri
    if settings.is_email_configured:
        em_status = "[bold green]TERHUBUNG[/bold green]"
        em_detail = f"{settings.email_imap_user} via {settings.email_imap_server}:{settings.email_imap_port}"
    else:
        em_status = "[bold red]BELUM AKTIF[/bold red]"
        em_detail = "Isi EMAIL_IMAP_USER dan EMAIL_IMAP_PASSWORD di .env"
    table.add_row("Email Mandiri (IMAP)", em_status, em_detail)

    # Gemini Vision
    if settings.is_gemini_configured:
        gm_status = "[bold green]TERHUBUNG[/bold green]"
        gm_detail = f"Model: {settings.gemini_model}"
    else:
        gm_status = "[bold yellow]MOCK / OFF[/bold yellow]"
        gm_detail = "GEMINI_API_KEY belum disetel (menggunakan mock engine untuk testing)"
    table.add_row("Gemini Vision (OCR)", gm_status, gm_detail)

    # SQLite Local Database
    db_path = settings.resolved_database_path
    if db_path.exists():
        db_status = "[bold green]SIAP[/bold green]"
        db_detail = f"{db_path} ({db_path.stat().st_size} bytes)"
    else:
        db_status = "[bold green]AUTO-CREATE[/bold green]"
        db_detail = f"Akan otomatis dibuat di {db_path}"
    table.add_row("Database SQLite", db_status, db_detail)

    console.print(table)


@cli.command()
def test_email() -> None:
    """Uji coba koneksi IMAP dan pemindaian email notifikasi Mandiri."""
    console.print("[cyan]Menguji koneksi ke server IMAP...[/cyan]")
    listener = EmailListener()

    if not settings.is_email_configured:
        console.print("[yellow]Peringatan: EMAIL_IMAP_USER dan PASSWORD belum disetel di .env.[/yellow]")
        console.print("Silakan isi .env terlebih dahulu.")
        return

    try:
        mail = listener.connect()
        mail.select(listener.folder)
        status, response = mail.search(None, "ALL")
        total_msgs = len(response[0].split()) if response and response[0] else 0
        mail.close()
        mail.logout()
        console.print(f"[bold green]Koneksi IMAP Berhasil![/bold green] Total email di folder {listener.folder}: {total_msgs}")
    except Exception as e:
        console.print(f"[bold red]Gagal terhubung ke IMAP:[/bold red] {e}")


@cli.command()
@click.argument("image_path", type=click.Path(exists=True))
def test_ocr(image_path: str) -> None:
    """Uji coba ekstraksi OCR screenshot bukti transaksi."""
    console.print(f"[cyan]Membaca berkas gambar: {image_path}...[/cyan]")
    p = Path(image_path)
    image_bytes = p.read_bytes()

    ext = p.suffix.lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"

    async def run_ocr():
        if settings.is_gemini_configured:
            console.print(f"[cyan]Menggunakan Gemini Vision ({settings.gemini_model})...[/cyan]")
            engine_ocr = GeminiVisionEngine()
        else:
            console.print("[yellow]GEMINI_API_KEY belum disetel, menggunakan MockOcrEngine...[/yellow]")
            engine_ocr = MockOcrEngine()

        tx = await engine_ocr.extract_transaction(image_bytes, mime_type=mime)
        return tx

    tx = asyncio.run(run_ocr())

    if tx:
        console.print(Panel.fit(
            f"[bold green]Ekstraksi Berhasil![/bold green]\n\n"
            f"Nominal: [bold]{tx.formatted_amount}[/bold]\n"
            f"Tipe: {tx.type.value}\n"
            f"Kategori: {tx.category}\n"
            f"Sumber Dana: {tx.source}\n"
            f"Keterangan/Merchant: {tx.description}\n"
            f"Tanggal/Jam: {tx.formatted_datetime}\n"
            f"No Referensi: {tx.reference_id or '-'}",
            title="Hasil Deteksi OCR",
        ))
    else:
        console.print("[bold red]Gagal mengekstrak data transaksi dari gambar.[/bold red]")


@cli.command()
def test_telegram() -> None:
    """Uji coba mengirim pesan ke akun Telegram pengguna."""
    console.print("[cyan]Mengirim pesan uji coba ke Telegram...[/cyan]")
    if not settings.is_telegram_configured:
        console.print("[bold red]TELEGRAM_BOT_TOKEN belum disetel di .env[/bold red]")
        return

    import asyncio
    from telegram import Bot

    async def send_test():
        bot = Bot(token=settings.telegram_bot_token)
        me = await bot.get_me()
        console.print(f"[bold green]Bot Terdeteksi:[/bold green] @{me.username} ({me.first_name})")

        for user_id in settings.allowed_user_ids:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text="👋 *Halo dari FinWidBot!*\n\nKoneksi Telegram Bot Anda telah *berhasil terhubung* ke sistem Finance Note! 🚀",
                    parse_mode="Markdown",
                )
                console.print(f" [green]✓[/green] Berhasil mengirim pesan uji coba ke User ID: {user_id}")
            except Exception as e:
                console.print(f" [red]✗[/red] Gagal mengirim pesan ke {user_id}: {e}")

    asyncio.run(send_test())


@cli.command()
def test_sheets() -> None:
    """Uji coba inisialisasi tab dan koneksi ke Google Sheets."""
    console.print("[cyan]Menguji koneksi ke Google Sheets...[/cyan]")
    if not sheets_client.is_configured():
        console.print("[bold yellow]Kredensial Google Sheets belum lengkap.[/bold yellow]")
        console.print("Pastikan credentials/service_account.json dan GOOGLE_SPREADSHEET_ID sudah diatur di .env.")
        return

    try:
        sheets_client.initialize_sheets()
        console.print("[bold green]Inisialisasi Google Sheets Berhasil![/bold green]")
        console.print("Tab 'Transaksi', 'Kategori', dan 'Dashboard' sudah aktif dengan format dan rumus.")
    except Exception as e:
        console.print(f"[bold red]Gagal menghubungkan Google Sheets:[/bold red] {e}")


@cli.command()
def simulate_flow() -> None:
    """Simulasikan alur kerja transaksi lengkap (Pencatatan -> Database -> Sheets)."""
    console.print(Panel.fit("[bold cyan]Simulasi Alur Transaksi Finance Note[/bold cyan]"))

    now = datetime.now()
    # 1. Transaksi GoPay
    tx_gopay = Transaction(
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M:%S"),
        type=TransactionType.PENGELUARAN,
        amount=38500.0,
        category="Makanan & Minuman",
        source=TransactionSource.GOPAY.value,
        description="Kopi Kenangan - Plaza Senayan",
        reference_id=f"GP-SIM-{now.strftime('%H%M%S')}",
        input_via="SCREENSHOT",
    )

    # 2. Transaksi Livin Mandiri
    tx_mandiri = Transaction(
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M:%S"),
        type=TransactionType.PENGELUARAN,
        amount=150000.0,
        category="Belanja",
        source=TransactionSource.LIVIN.value,
        description="SUPERINDO JAKARTA",
        reference_id=f"MANDIRI-SIM-{now.strftime('%H%M%S')}",
        input_via="EMAIL",
    )

    # 3. Transaksi Pemasukan
    tx_masuk = Transaction(
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M:%S"),
        type=TransactionType.PEMASUKAN,
        amount=5000000.0,
        category="Gaji",
        source=TransactionSource.LIVIN.value,
        description="GAJI BULANAN PT TEKNOLOGI",
        reference_id=f"PAYROLL-SIM-{now.strftime('%H%M%S')}",
        input_via="EMAIL",
    )

    for tx in [tx_gopay, tx_mandiri, tx_masuk]:
        sheets_client.append_transaction(tx)
        console.print(f" [green]✓[/green] Dicatat: [{tx.type.value}] [bold]{tx.formatted_amount}[/bold] - {tx.description} ({tx.source})")

    # Ambil rekap bulanan
    summary = sheets_client.get_monthly_summary(now.year, now.month)
    console.print("\n[bold cyan]Rekapitulasi Hasil Simulasi:[/bold cyan]")
    console.print(f"Total Pemasukan: [green]{summary.formatted_income}[/green]")
    console.print(f"Total Pengeluaran: [red]{summary.formatted_expense}[/red]")
    console.print(f"Net Cashflow: [bold]{summary.formatted_net}[/bold]")
    console.print(f"Total Transaksi: {summary.transaction_count}")


@cli.command()
def summary() -> None:
    """Tampilkan rekap kas bulanan saat ini."""
    now = datetime.now()
    s = sheets_client.get_monthly_summary(now.year, now.month)

    table = Table(title=f"Rekap Arus Kas Bulan Ini ({now.strftime('%B %Y')})")
    table.add_column("Metrik", style="bold")
    table.add_column("Nilai", justify="right")

    table.add_row("Total Pemasukan", f"[green]{s.formatted_income}[/green]")
    table.add_row("Total Pengeluaran", f"[red]{s.formatted_expense}[/red]")
    table.add_row("Net Cashflow", f"[bold]{s.formatted_net}[/bold]")
    table.add_row("Jumlah Transaksi", str(s.transaction_count))

    console.print(table)


if __name__ == "__main__":
    cli()
