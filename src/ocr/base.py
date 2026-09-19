"""Base interface untuk engine OCR / Vision AI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.models import Transaction


class BaseOcrEngine(ABC):
    """Kelas abstrak dasar untuk mengekstrak transaksi dari gambar screenshot."""

    @abstractmethod
    async def extract_transaction(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> Optional[Transaction]:
        """Ekstraksi data transaksi dari data biner gambar."""
        pass
