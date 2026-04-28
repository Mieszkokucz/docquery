"""Ekstrakcja treści z PDF via Claude Vision z cache'owaniem per-rozdział."""

from __future__ import annotations

import logging
from pathlib import Path

import anthropic
import pymupdf

from backend.app.config import VISION_CACHE_DIR, VISION_MODEL
from backend.app.document.extraction_cache import (
    chapter_cache_path,
    chapter_is_complete,
    load_cached_chapters,
)
from backend.app.document.image_renderer import apply_cropboxes, page_to_base64
from backend.app.document.models import (
    ExtractedChapter,
    ExtractedDocument,
    ExtractedPage,
)
from backend.app.document.structure_extractor import extract_structure
from backend.app.document.vision_prompt import (
    VISION_SYSTEM_PROMPT_v2 as VISION_SYSTEM_PROMPT,
)
from backend.app.document.vision_response import (
    build_section_hint,
    clean_response,
    normalize_heading_texts,
    promote_matching_subsection_headers,
    reclassify_spurious_section_headers,
    vision_elements_to_blocks,
)

logger = logging.getLogger(__name__)


def _extract_via_vision(
    client: anthropic.Anthropic,
    doc: pymupdf.Document,
    extracted_page: ExtractedPage,
    model: str = VISION_MODEL,
    user_prompt: str = "",
) -> str:
    """Wysyła stronę jako obraz do Claude Vision i zwraca surową odpowiedź."""
    image_b64, media_type = page_to_base64(doc, extracted_page)

    content: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_b64,
            },
        },
    ]
    if user_prompt:
        content.append({"type": "text", "text": user_prompt})

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=VISION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    return response.content[0].text


def _extract_single_chapter(
    client: anthropic.Anthropic,
    chapter: ExtractedChapter,
    doc: pymupdf.Document,
    model: str = VISION_MODEL,
    ch_path: Path | None = None,
) -> None:
    """Ekstrahuje treść z jednego rozdziału, pomijając title page
    oraz strony które zawierają już bloki treści.

    Modyfikuje chapter in-place. Błędy pojedynczych stron są logowane jako
    WARNING i pomijane — nie przerywają przetwarzania pozostałych stron.
    Po każdej udanej stronie zapisuje incremental cache do ch_path (jeśli podany).
    """
    pages = chapter.pages[1:]
    needed = [p for p in pages if not p.blocks]
    if not needed:
        logger.info(
            "[cache] %s — %d stron (wszystkie w cache)", chapter.title, len(pages)
        )
        return

    logger.info(
        "--- %s (%d nowych / %d stron) ---", chapter.title, len(needed), len(pages)
    )

    apply_cropboxes(doc, needed)

    for i, page in enumerate(needed):
        hint = build_section_hint(page)
        logger.info("  [%d/%d] Strona %d...", i + 1, len(needed), page.page_num)
        try:
            raw = _extract_via_vision(client, doc, page, model=model, user_prompt=hint)
            parsed = clean_response(raw)
            elements = parsed.get("elements", [])
            page.blocks = vision_elements_to_blocks(page.page_num, elements)
            normalized = normalize_heading_texts(page)
            if normalized:
                logger.info(
                    "  [postprocess] p%d: %d nagłówków znormalizowanych (\\n→spacja)",
                    page.page_num,
                    normalized,
                )
            spurious = reclassify_spurious_section_headers(page)
            if spurious:
                logger.info(
                    "  [postprocess] p%d: %d section-header → subsection-header",
                    page.page_num,
                    spurious,
                )
            promoted = promote_matching_subsection_headers(page)
            if promoted:
                logger.info(
                    "  [postprocess] p%d: %d subsection-header → section-header",
                    page.page_num,
                    promoted,
                )
        except Exception as exc:
            logger.warning(
                "  [%d/%d] Strona %d: błąd ekstrakcji — %s. Strona pominięta.",
                i + 1,
                len(needed),
                page.page_num,
                exc,
            )
            continue
        if ch_path is not None:
            chapter.save_json(ch_path)


def extract_all_chapters(
    document: ExtractedDocument,
    doc: pymupdf.Document,
    model: str = VISION_MODEL,
    cache_dir: Path = VISION_CACHE_DIR,
) -> ExtractedDocument:
    """Ekstrahuje bloki ze wszystkich rozdziałów — cache zapisywany per-chapter."""
    client = anthropic.Anthropic()
    cache_dir.mkdir(parents=True, exist_ok=True)

    for chapter in document.chapters:
        if chapter_is_complete(chapter):
            logger.info("[cache] %s — pomijam (już w pamięci)", chapter.title)
            continue
        ch_path = chapter_cache_path(cache_dir, chapter.chapter_id)
        _extract_single_chapter(client, chapter, doc, model=model, ch_path=ch_path)
        chapter.save_json(ch_path)
        logger.info("[saved] %s → %s", chapter.title, ch_path.name)

    return document


def load_or_extract(
    pdf_path: str | Path,
    cache_dir: Path = VISION_CACHE_DIR,
) -> ExtractedDocument:
    """Ładuje z per-chapter cache jeśli kompletne; inaczej uruchamia ekstrakcję Vision.

    Returns: ExtractedDocument z wypełnionymi blokami.
    """
    pdf_path = Path(pdf_path)
    document, doc = extract_structure(pdf_path)

    load_cached_chapters(document, cache_dir)

    uncached = [ch for ch in document.chapters if not chapter_is_complete(ch)]
    if uncached:
        logger.info("%d rozdziałów do ekstrakcji...", len(uncached))
        extract_all_chapters(document, doc, cache_dir=cache_dir)
    else:
        logger.info("Wszystkie rozdziały w cache — pomijam ekstrakcję Vision")

    doc.close()
    return document
