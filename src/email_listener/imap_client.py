"""Klien IMAP untuk memantau email notifikasi Bank Mandiri secara realtime."""

from __future__ import annotations

import asyncio
import email
from email.header import decode_header
import imaplib
import logging
from typing import Callable, Coroutine, Optional

from src.config import settings
from src.database import db
from src.email_listener.mandiri_parser import is_mandiri_transaction_email, parse_mandiri_email
from src.models import Transaction

logger = logging.getLogger(__name__)


def decode_str(header_val: str) -> str:
    """Dekode header email MIME ke string utf-8 bersih."""
    if not header_val:
        return ""
    try:
        decoded_list = decode_header(header_val)
        result = []
        for text, encoding in decoded_list:
            if isinstance(text, bytes):
                enc = encoding or "utf-8"
                try:
                    result.append(text.decode(enc, errors="replace"))
                except LookupError:
                    result.append(text.decode("utf-8", errors="replace"))
            else:
                result.append(str(text))
        return " ".join(result)
    except Exception:
        return str(header_val)


class EmailListener:
    """Pemantau email berbasis IMAP untuk transaksi Livin Mandiri."""

    def __init__(self) -> None:
        self.server = settings.email_imap_server
        self.port = settings.email_imap_port
        self.user = settings.email_imap_user
        self.password = settings.email_imap_password
        self.folder = settings.email_imap_folder
        self.check_interval = settings.email_check_interval_seconds
        self._is_running = False

    def connect(self) -> imaplib.IMAP4_SSL:
        """Membuka koneksi aman SSL ke server IMAP."""
        mail = imaplib.IMAP4_SSL(self.server, self.port)
        mail.login(self.user, self.password)
        return mail

    def check_new_emails(
        self,
        on_transaction_found: Optional[Callable[[Transaction], Coroutine]] = None,
    ) -> list[Transaction]:
        """Memeriksa email baru yang belum dibaca atau belum diproses.

        Sinkron/blocking, dipanggil dalam thread pool jika di async.
        """
        if not settings.is_email_configured:
            logger.info("Email IMAP belum dikonfigurasi. Melewati pengecekan email.")
            return []

        transactions_found: list[Transaction] = []

        try:
            mail = self.connect()
            mail.select(self.folder)

            # Cari email belum dibaca (UNSEEN)
            status, response = mail.search(None, "UNSEEN")
            msg_nums = response[0].split()

            # Jika tidak ada yang UNSEEN, coba cari email Mandiri 5 terakhir untuk pengecekan
            if not msg_nums:
                status, response = mail.search(None, f'(FROM "{settings.email_mandiri_sender}")')
                if response and response[0]:
                    msg_nums = response[0].split()[-5:]

            for num in msg_nums:
                try:
                    status, data = mail.fetch(num, "(RFC822)")
                    if status != "OK" or not data or not data[0]:
                        continue

                    raw_email = data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    message_id = msg.get("Message-ID", f"MSG-{num.decode()}")
                    subject = decode_str(msg.get("Subject", ""))
                    sender = decode_str(msg.get("From", ""))
                    date_str = msg.get("Date", "")

                    # Cek deduplikasi
                    if db.is_email_processed(message_id):
                        continue

                    # Ambil isi teks / HTML email
                    body_content = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            if "attachment" not in content_disposition:
                                if content_type in ["text/html", "text/plain"]:
                                    charset = part.get_content_charset() or "utf-8"
                                    try:
                                        payload = part.get_payload(decode=True)
                                        body_content += payload.decode(charset, errors="replace") + "\n"
                                    except Exception:
                                        pass
                    else:
                        charset = msg.get_content_charset() or "utf-8"
                        try:
                            payload = msg.get_payload(decode=True)
                            body_content = payload.decode(charset, errors="replace")
                        except Exception:
                            body_content = str(msg.get_payload())

                    # Validasi apakah ini email transaksi Mandiri
                    if not is_mandiri_transaction_email(subject, body_content, sender):
                        # Tandai agar tidak dicek ulang
                        db.mark_email_processed(message_id, subject, sender, date_str)
                        continue

                    # Parse transaksi
                    tx = parse_mandiri_email(subject, body_content, message_id)
                    if tx:
                        # Tandai email berhasil diproses
                        db.mark_email_processed(message_id, subject, sender, date_str)
                        transactions_found.append(tx)
                        logger.info(f"Transaksi Mandiri ditemukan dari email: {tx.formatted_amount} ({tx.description})")

                except Exception as ex:
                    logger.error(f"Gagal memproses email #{num}: {ex}", exc_info=True)

            mail.close()
            mail.logout()

        except Exception as e:
            logger.error(f"Kesalahan koneksi IMAP: {e}")

        return transactions_found

    async def start_listening(
        self,
        on_transaction_found: Callable[[Transaction], Coroutine],
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """Memulai loop asinkron pemantau email berkala."""
        self._is_running = True
        logger.info(
            f"Email listener aktif. Memeriksa email setiap {self.check_interval} detik..."
        )

        while self._is_running:
            if stop_event and stop_event.is_set():
                break

            try:
                # Jalankan fungsi blocking di background thread executor
                transactions = await asyncio.to_thread(self.check_new_emails)
                for tx in transactions:
                    try:
                        await on_transaction_found(tx)
                    except Exception as err:
                        logger.error(f"Gagal mengeksekusi callback transaksi: {err}", exc_info=True)

            except Exception as e:
                logger.error(f"Error pada loop email listener: {e}")

            # Tunggu interval berikutnya
            try:
                if stop_event:
                    await asyncio.wait_for(stop_event.wait(), timeout=self.check_interval)
                    break
                else:
                    await asyncio.sleep(self.check_interval)
            except asyncio.TimeoutError:
                pass

        logger.info("Email listener berhenti.")

    def stop(self) -> None:
        """Hentikan pemantauan email."""
        self._is_running = False
