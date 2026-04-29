"""Wspólny bootstrap pipeline'u v2: load cache vision → chunk → index."""

from __future__ import annotations

from backend.app.config import (
    V2_CHUNK_MAX_CHARS,
    V2_CHUNK_OVERLAP_CHARS,
    VISION_CACHE_DIR,
)
from backend.app.document.chunker_v2 import chunk_document
from backend.app.document.models import (
    DocumentMetadata,
    ExtractedChapter,
    ExtractedDocument,
)
from backend.app.retrieval.vector_store_v2 import index_v2_chunks

CHAPTER_ORDER = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


def load_and_index_v2_corpus() -> int:
    """Ładuje cache vision, chunkuje i indeksuje. Zwraca liczbę chunków.

    Raises:
        RuntimeError: jeśli `VISION_CACHE_DIR` jest pusty.
    """
    chapters = [
        ExtractedChapter.load_json(VISION_CACHE_DIR / f"{cid}.json")
        for cid in CHAPTER_ORDER
        if (VISION_CACHE_DIR / f"{cid}.json").exists()
    ]
    if not chapters:
        raise RuntimeError(
            f"Brak rozdziałów w cache {VISION_CACHE_DIR}. "
            "Uruchom ekstrakcję vision (scripts/...) przed startem."
        )

    doc = ExtractedDocument(
        metadata=DocumentMetadata(
            source_file="raport_2024_pl.pdf",
            total_pages=sum(len(ch.pages) for ch in chapters),
            extraction_date="cache",
        ),
        title="BGK 2024",
        chapters=chapters,
    )
    chunks = chunk_document(
        doc, max_chars=V2_CHUNK_MAX_CHARS, overlap_chars=V2_CHUNK_OVERLAP_CHARS
    )
    index_v2_chunks(chunks)
    return len(chunks)
