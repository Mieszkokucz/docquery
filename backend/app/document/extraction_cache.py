"""Cache per-rozdział dla vision_extractor — JSON I/O + sprawdzenie kompletności."""

from __future__ import annotations

import logging
from pathlib import Path

from backend.app.document.models import ExtractedChapter, ExtractedDocument

logger = logging.getLogger(__name__)


def chapter_cache_path(cache_dir: Path, chapter_id: str) -> Path:
    return cache_dir / f"{chapter_id}.json"


def chapter_is_complete(chapter: ExtractedChapter) -> bool:
    """Sprawdza, czy każda nie-tytułowa strona rozdziału ma wyekstrahowane bloki."""
    return all(bool(p.blocks) for p in chapter.pages[1:])


def load_cached_chapters(document: ExtractedDocument, cache_dir: Path) -> None:
    """Dla każdego rozdziału document, jeśli istnieje cache — wczytuje go in-place."""
    for chapter in document.chapters:
        ch_path = chapter_cache_path(cache_dir, chapter.chapter_id)
        if ch_path.exists():
            cached = ExtractedChapter.load_json(ch_path)
            chapter.pages = cached.pages
            logger.info("[cache] %s — wczytano z %s", chapter.title, ch_path.name)
