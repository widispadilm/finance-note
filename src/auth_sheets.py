"""Skrip otorisasi Google Sheets interaktif (OAuth 2.0) yang handal."""

from __future__ import annotations

import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import webbrowser

# Pastikan console Windows utf-8 dan unbuffered
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

from google_auth_oauthlib.flow import InstalledAppFlow
from rich.console import Console
from rich.panel import Panel

from src.config import settings
from src.sheets.client import sheets_client

console = Console()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

PORT = 8080
REDIRECT_URI = f"http://localhost:{PORT}/"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handler HTTP sederhana untuk menangkap kode otorisasi dari Google."""

    auth_code: str = ""
    error: str = ""

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_url.query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            success_html = """
            <html>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f0fdf4;">
                <h1 style="color: #16a34a;">✅ Otorisasi Google Sheets Berhasil!</h1>
                <p style="font-size: 18px; color: #374151;">Token berhasil disimpan. Tab Transaksi, Kategori, dan Dashboard sedang diinisialisasi.</p>
                <p style="color: #6b7280;">Anda dapat menutup tab browser ini dan kembali ke aplikasi.</p>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode("utf-8"))
        elif "error" in params:
            OAuthCallbackHandler.error = params["error"][0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            err_msg = params.get("error_description", [OAuthCallbackHandler.error])[0]
            self.wfile.write(f"<h1>Gagal Otorisasi: {err_msg}</h1>".encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Mute logging HTTP standar agar tidak mengotori terminal
        return


def authorize_interactive() -> None:
    """Jalankan flow otorisasi browser interaktif."""
    secret_path = settings.resolved_client_secret_path
    if not secret_path.exists():
        console.print(f"[bold red]Berkas {secret_path} tidak ditemukan![/bold red]")
        return

    console.print(Panel.fit(
        "[bold cyan]Otorisasi Google Sheets (OAuth 2.0)[/bold cyan]\n"
        "Menyiapkan tautan login Google...",
    ))

    flow = InstalledAppFlow.from_client_secrets_file(
        str(secret_path),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

    # Simpan link ke file agar bisa dibaca kapan saja
    link_file = Path("data/auth_url.txt")
    link_file.parent.mkdir(parents=True, exist_ok=True)
    link_file.write_text(auth_url, encoding="utf-8")

    console.print(f"\n[bold green]🌐 SILAKAN BUKA TAUTAN INI DI BROWSER:[/bold green]\n{auth_url}\n")

    # Coba buka otomatis di browser
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    console.print(f"[cyan]Server lokal aktif di {REDIRECT_URI}. Menunggu konfirmasi login...[/cyan]")

    # Mulai server HTTP lokal
    server = HTTPServer(("127.0.0.1", PORT), OAuthCallbackHandler)
    server.timeout = 180  # timeout 3 menit

    while not OAuthCallbackHandler.auth_code and not OAuthCallbackHandler.error:
        server.handle_request()

    server.server_close()

    if OAuthCallbackHandler.auth_code:
        console.print("[cyan]Menukarkan kode otorisasi dengan token akses Google...[/cyan]")
        flow.fetch_token(code=OAuthCallbackHandler.auth_code)
        creds = flow.credentials

        # Simpan authorized_user.json
        user_path = settings.resolved_authorized_user_path
        user_path.parent.mkdir(parents=True, exist_ok=True)
        user_path.write_text(creds.to_json())
        console.print(f"[bold green]✓ Berhasil![/bold green] Token tersimpan di: {user_path}")

        # Inisialisasi tab sheet
        console.print("[cyan]Menginisialisasi tab Transaksi, Kategori, dan Dashboard di Google Sheets...[/cyan]")
        sheets_client.initialize_sheets()
        console.print("[bold green]✓ Tab Google Sheets berhasil diinisialisasi dan siap digunakan![/bold green]")
    else:
        console.print(f"[bold red]Gagal otorisasi:[/bold red] {OAuthCallbackHandler.error}")


if __name__ == "__main__":
    authorize_interactive()
