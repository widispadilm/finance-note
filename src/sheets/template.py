"""Definisi template dan struktur tab Google Sheets untuk pencatatan keuangan."""

from __future__ import annotations

from typing import Any
import gspread

from src.models import DEFAULT_EXPENSE_CATEGORIES, DEFAULT_INCOME_CATEGORIES

TRANSAKSI_HEADERS = [
    "ID",
    "Waktu",
    "Tanggal",
    "Jam",
    "Tipe",
    "Kategori",
    "Nominal (Rp)",
    "Sumber Dana",
    "Merchant / Keterangan",
    "No. Referensi",
    "Input Via",
    "Status",
]


def setup_transaksi_tab(worksheet: gspread.Worksheet) -> None:
    """Setup tab Transaksi dengan header dan format freeze."""
    rows = worksheet.get_all_values()
    if not rows or len(rows) == 0:
        worksheet.append_row(TRANSAKSI_HEADERS)
    elif rows[0] != TRANSAKSI_HEADERS:
        worksheet.insert_row(TRANSAKSI_HEADERS, index=1)

    try:
        # Format header menjadi tebal dan freeze baris 1
        worksheet.format("A1:L1", {
            "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
            "backgroundColor": {"red": 0.12, "green": 0.35, "blue": 0.58},
            "horizontalAlignment": "CENTER",
        })
        worksheet.freeze(rows=1)
    except Exception:
        pass


def setup_kategori_tab(worksheet: gspread.Worksheet) -> None:
    """Setup tab Kategori dengan daftar kategori pengeluaran dan pemasukan default."""
    rows = worksheet.get_all_values()
    if not rows or len(rows) == 0:
        headers = ["Tipe", "Kategori", "Anggaran Bulanan (Rp)"]
        initial_data = [headers]

        for cat in DEFAULT_EXPENSE_CATEGORIES:
            initial_data.append(["PENGELUARAN", cat, 0])

        for cat in DEFAULT_INCOME_CATEGORIES:
            initial_data.append(["PEMASUKAN", cat, 0])

        worksheet.update("A1", initial_data)
        try:
            worksheet.format("A1:C1", {
                "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
                "backgroundColor": {"red": 0.20, "green": 0.45, "blue": 0.35},
                "horizontalAlignment": "CENTER",
            })
            worksheet.freeze(rows=1)
        except Exception:
            pass


def setup_dashboard_tab(
    worksheet: gspread.Worksheet,
    tab_transaksi: str = "Transaksi",
) -> None:
    """Setup tab Dashboard dengan rumus kalkulasi otomatis arus kas."""
    rows = worksheet.get_all_values()
    if not rows or len(rows) <= 1:
        worksheet.clear()

        # Matriks data awal dashboard dengan rumus Google Sheets
        dashboard_content: list[list[Any]] = [
            ["📊 RINGKASAN ARUS KAS & CASHFLOW PRIBADI", "", "", "", "", ""],
            ["", "", "", "", "", ""],
            ["METRIK UTAMA", "JUMLAH (RP)", "", "PENGELUARAN PER SUMBER", "TOTAL (RP)", ""],
            [
                "Total Pemasukan",
                f'=SUMIF({tab_transaksi}!E:E, "PEMASUKAN", {tab_transaksi}!G:G)',
                "",
                "Livin' Mandiri",
                f'=SUMIFS({tab_transaksi}!G:G, {tab_transaksi}!E:E, "PENGELUARAN", {tab_transaksi}!H:H, "*Livin*")',
                "",
            ],
            [
                "Total Pengeluaran",
                f'=SUMIF({tab_transaksi}!E:E, "PENGELUARAN", {tab_transaksi}!G:G)',
                "",
                "GoPay",
                f'=SUMIFS({tab_transaksi}!G:G, {tab_transaksi}!E:E, "PENGELUARAN", {tab_transaksi}!H:H, "*GoPay*")',
                "",
            ],
            [
                "Sisa Kas / Net Cashflow",
                "=B4-B5",
                "",
                "QRIS",
                f'=SUMIFS({tab_transaksi}!G:G, {tab_transaksi}!E:E, "PENGELUARAN", {tab_transaksi}!H:H, "*QRIS*")',
                "",
            ],
            [
                "",
                "",
                "",
                "Sumber Lainnya",
                f'=SUMIFS({tab_transaksi}!G:G, {tab_transaksi}!E:E, "PENGELUARAN", {tab_transaksi}!H:H, "*Lainnya*")',
                "",
            ],
            ["", "", "", "", "", ""],
            ["RINCIAN PENGELUARAN PER KATEGORI", "", "", "", "", ""],
            ["Kategori", "Total (Rp)", "% dari Total", "", "", ""],
        ]

        # Tambahkan baris per kategori
        start_row = 11
        for idx, cat in enumerate(DEFAULT_EXPENSE_CATEGORIES):
            curr_row = start_row + idx
            formula_sum = f'=SUMIFS({tab_transaksi}!G:G, {tab_transaksi}!E:E, "PENGELUARAN", {tab_transaksi}!F:F, A{curr_row})'
            formula_pct = f'=IF($B$5>0, B{curr_row}/$B$5, 0)'
            dashboard_content.append([cat, formula_sum, formula_pct, "", "", ""])

        worksheet.update("A1", dashboard_content, value_input_option="USER_ENTERED")

        try:
            # Styling judul
            worksheet.format("A1:F1", {
                "textFormat": {"bold": True, "fontSize": 14},
            })
            # Styling header metrik
            worksheet.format("A3:B3", {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
            })
            worksheet.format("D3:E3", {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
            })
            worksheet.format("A10:C10", {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
            })
        except Exception:
            pass
