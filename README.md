# 💰 Finance Note - Sistem Pencatatan Keuangan Otomatis

Sistem otomasi pencatatan arus kas (*cashflow*: pemasukan & pengeluaran) pribadi secara *realtime* dari dua kanal utama:
1. **Bank Mandiri (Livin' by Mandiri)**: Data mutasi dan transaksi ditarik otomatis dari email notifikasi secara *realtime* (via IMAP/Gmail).
2. **GoPay & Bukti Lainnya**: Ekstraksi otomatis dari gambar *screenshot* bukti pembayaran / transfer via **Telegram Bot** menggunakan teknologi **OCR & Multimodal Vision AI (Google Gemini)**.
3. **Penyimpanan Realtime di Google Sheets**: Seluruh transaksi otomatis terangkum ke Google Sheets lengkap dengan rumus rekap kas bulanan, breakdown per kategori, dan per sumber dana.
4. **Interaksi Penuh via Telegram Bot**: Notifikasi instan setiap kali ada mutasi baru, tombol interaktif ubah kategori, konfirmasi simpan, input teks bahasa alami, dan perintah rekap saldo.

---

## 🌟 Fitur Utama

- 📬 **Realtime Livin' Email Parser**: Membaca email notifikasi Bank Mandiri (Debit, Kredit, QRIS, Transfer Keluar, Top Up GoPay) tanpa jeda.
- 📸 **AI Multimodal OCR (Gemini Vision)**: Membaca screenshot resi GoPay, QRIS, BCA, OVO, ShopeePay, DANA, hingga struk belanja fisik dengan akurasi tinggi.
- 📊 **Realtime Google Sheets Sync**:
  - **Tab `Transaksi`**: Kolom `[ID, Waktu, Tanggal, Jam, Tipe, Kategori, Nominal, Sumber Dana, Merchant/Keterangan, No. Referensi, Input Via, Status]`.
  - **Tab `Kategori`**: Kategori pengeluaran & pemasukan standar beserta target anggaran bulanan.
  - **Tab `Dashboard`**: Formula otomatis (`SUMIFS`, total pemasukan, total pengeluaran, sisa saldo, breakdown sumber dana, dan grafik persentase kategori).
- 🤖 **Telegram Bot Interaktif**:
  - Kirim foto/screenshot -> bot langsung memindai dan menampilkan kartu konfirmasi dengan tombol: `[✅ Simpan]`, `[✏️ Ubah Kategori]`, `[❌ Batalkan]`.
  - Notifikasi instan saat email Mandiri masuk dengan tombol `[✏️ Ubah Kategori]`.
  - Catat cepat bahasa alami (misal: *"makan bakso 25rb gopay"* atau *"/keluar 50000 bensin"*).
  - Perintah informasi kas: `/saldo`, `/rekap`, `/riwayat`, `/sheet`.
- 🛡️ **Deduplikasi Anti-Dobel**: Database SQLite lokal menyimpan `Message-ID` email dan nomor referensi transaksi sehingga tidak akan ada transaksi yang tercatat dobel meski bot direstart.
- 🧪 **Built-in Mock & CLI Suite**: Seluruh sistem dapat diuji coba seketika bahkan sebelum Anda memasukkan API key asli.

---

## 📁 Struktur Direktori

```
d:\Projects\Finance Note/
├── .env.example                # Template konfigurasi variabel lingkungan
├── .gitignore                  # Berkas yang diabaikan Git
├── pyproject.toml              # Definisi dependensi proyek
├── README.md                   # Dokumentasi panduan lengkap
├── credentials/                # Tempat menyimpan service_account.json
│   └── .gitkeep
├── data/                       # Database SQLite lokal & cache
│   └── finance.db
├── src/
│   ├── __init__.py
│   ├── config.py               # Pengaturan konfigurasi & validasi environment
│   ├── database.py             # SQLite helper untuk deduplikasi & riwayat
│   ├── models.py               # Pydantic data models & helper Rupiah
│   ├── core/
│   │   ├── __init__.py
│   │   ├── categorizer.py      # Aturan pencocokan kata kunci kategori Indonesia
│   │   └── engine.py           # Orkestrator alur transaksi
│   ├── email_listener/
│   │   ├── __init__.py
│   │   ├── imap_client.py      # Pemantau email IMAP berkala
│   │   └── mandiri_parser.py   # Parser email transaksi Bank Mandiri
│   ├── ocr/
│   │   ├── __init__.py
│   │   ├── base.py             # Interface dasar OCR
│   │   ├── gemini_vision.py    # Ekstraksi multimodal Gemini 2.0 / 1.5 Flash
│   │   └── mock_engine.py      # Engine tiruan untuk simulasi & unit test
│   ├── sheets/
│   │   ├── __init__.py
│   │   ├── client.py           # Wrapper gspread Google Sheets
│   │   └── template.py         # Struktur tab, rumus SUMIFS, dan styling
│   ├── telegram_bot/
│   │   ├── __init__.py
│   │   ├── bot.py              # Inisialisasi python-telegram-bot
│   │   ├── formatters.py       # Pembuat kartu pesan Markdown & inline keyboard
│   │   └── handlers.py         # Handler foto, perintah, teks manual & callback
│   ├── cli.py                  # Alat diagnostik & simulasi terminal
│   └── main.py                 # Entrypoint utama menjalankan seluruh servis
└── tests/                      # Rangkaian automated unit test (100% pass)
    ├── test_categorizer.py
    ├── test_database.py
    ├── test_engine_and_manual.py
    ├── test_mandiri_parser.py
    └── test_models.py
```

---

## 🚀 Panduan Setup & Konfigurasi

### 1. Persiapan Kredensial

Salin file `.env.example` menjadi `.env`:
```powershell
cp .env.example .env
```

Buka `.env` dan lengkapi bagian berikut:

#### A. Bot Telegram
1. Buka Telegram dan cari bot `@BotFather`.
2. Ketik `/newbot`, ikuti petunjuk, lalu salin **API Token** ke `TELEGRAM_BOT_TOKEN`.
3. Cari bot `@userinfobot` di Telegram untuk mengetahui User ID akun Telegram Anda.
4. Masukkan ID tersebut ke `ALLOWED_TELEGRAM_USER_IDS` (misal: `123456789`).

#### B. Google Sheets
1. Buka [Google Cloud Console](https://console.cloud.google.com/).
2. Buat proyek baru, lalu aktifkan **Google Sheets API** dan **Google Drive API**.
3. Buat **Service Account**, lalu unduh berkas kunci berupa `.json`.
4. Letakkan berkas tersebut di `credentials/service_account.json`.
5. Buat Google Spreadsheet baru di browser, lalu bagikan (*Share*) spreadsheet tersebut ke email Service Account (berakhiran `@...gserviceaccount.com`) sebagai **Editor**.
6. Salin Spreadsheet ID dari URL (bagian antara `/d/` dan `/edit`) ke `GOOGLE_SPREADSHEET_ID` di `.env`.

#### C. Email Livin' Mandiri (Gmail IMAP)
1. Gunakan akun Gmail tempat Anda menerima notifikasi mutasi Bank Mandiri.
2. Aktifkan verifikasi 2 langkah di Google Account Anda.
3. Buka **Google Account -> Security -> App Passwords** (Sandi Aplikasi).
4. Buat sandi aplikasi baru (16 karakter), lalu masukkan ke `EMAIL_IMAP_PASSWORD` di `.env`.
5. Isi `EMAIL_IMAP_USER` dengan alamat Gmail Anda.

#### D. Gemini API Key (Vision OCR)
1. Dapatkan API Key gratis di [Google AI Studio](https://aistudio.google.com/).
2. Salin API Key ke `GEMINI_API_KEY` di `.env`.

---

## 💻 Penggunaan & Perintah CLI

Proyek ini telah dilengkapi dengan *Virtual Environment* dan dependensi yang terinstal melalui `uv`.

### 1. Menjalankan Automated Tests
Pastikan semua unit test berjalan normal:
```powershell
.venv\Scripts\pytest -v
```

### 2. Memeriksa Status Konfigurasi
Periksa status integrasi seluruh modul:
```powershell
.venv\Scripts\python -m src.cli status
```

### 3. Menjalankan Simulasi Transaksi Penuh
Uji alur pencatatan dari GoPay, Livin Mandiri, hingga rekap kas tanpa perlu mengirim data asli:
```powershell
.venv\Scripts\python -m src.cli simulate-flow
```

### 4. Mengetes Ekstraksi OCR Gambar Screenshot
Uji coba membaca gambar screenshot bukti transaksi tertentu:
```powershell
.venv\Scripts\python -m src.cli test-ocr path/to/screenshot.jpg
```

### 5. Menginisialisasi Tab Google Sheets
Buat otomatis tab `Transaksi`, `Kategori`, dan `Dashboard` di Google Sheets Anda:
```powershell
.venv\Scripts\python -m src.cli test-sheets
```

### 6. Menjalankan Aplikasi Utama (Produksi)
Jalankan bot Telegram dan pemantau email Mandiri secara bersamaan:
```powershell
.venv\Scripts\python -m src.main
```

---

## 📱 Panduan Penggunaan Telegram Bot

Setelah aplikasi berjalan, buka bot Telegram Anda dan nikmati fitur-fiturnya:

### 1. Mengirim Screenshot Pembayaran (GoPay / QRIS / Transfer)
- Cukup kirim gambar tangkapan layar (screenshot) bukti pembayaran ke bot.
- Bot akan menampilkan kartu hasil analisis OCR:
  ```
  🧾 Bukti Transaksi Terdeteksi
  ━━━━━━━━━━━━━━━━━━━━━
  💸 Tipe: 🔴 Pengeluaran
  💰 Nominal: Rp 38.500
  🏷 Kategori: Makanan & Minuman
  💳 Sumber: GoPay
  🏪 Keterangan: Kopi Kenangan
  📅 Waktu: 2026-09-19 09:15:00
  🔖 No. Ref: GP-20260919-8812
  📌 Status: ⏳ Menunggu Konfirmasi
  ━━━━━━━━━━━━━━━━━━━━━
  [✅ Simpan ke Sheet] [✏️ Ubah Kategori] [❌ Batalkan]
  ```
- Klik **✅ Simpan ke Sheet** untuk langsung memasukkan ke baris Google Sheets.

### 2. Notifikasi Otomatis Email Livin' Mandiri
- Begitu Bank Mandiri mengirimkan email notifikasi transaksi ke email Anda, sistem langsung mencatatnya ke Google Sheets dan mengirimkan notifikasi ke Telegram:
  ```
  🧾 Notifikasi Transaksi Livin' Mandiri
  ━━━━━━━━━━━━━━━━━━━━━
  💸 Tipe: 🔴 Pengeluaran
  💰 Nominal: Rp 75.000
  🏷 Kategori: Makanan & Minuman
  💳 Sumber: Livin' Mandiri (QRIS)
  🏪 Keterangan: QRIS KOPI KENANGAN JAKARTA
  📅 Waktu: 2026-09-19 08:30:15
  🔖 No. Ref: 2026091912345678
  📌 Status: ✅ Tercatat di Sheets
  ━━━━━━━━━━━━━━━━━━━━━
  [✏️ Ubah Kategori]
  ```

### 3. Input Manual Cepat & Bahasa Alami
Ketik langsung pesan santai:
- `makan siang 35rb gopay`
- `beli bensin 50000 mandiri`
- `/keluar 25000 Kopi Kenangan (GoPay)`
- `/masuk 5000000 Gaji Bulanan`

### 4. Perintah Laporan Kas
- `/saldo` atau `/summary` : Melihat total pemasukan, pengeluaran, dan net cashflow bulan ini.
- `/rekap` : Rincian pengeluaran per kategori lengkap dengan visualisasi persentase bar `[████░░░░░░]`.
- `/riwayat` : Menampilkan 5 riwayat transaksi terakhir yang tersimpan.
- `/sheet` : Mengirim tautan langsung untuk membuka spreadsheet Google Sheets Anda.
