"""Parsing odpowiedzi Claude Vision — JSON → ExtractedBlock."""

from __future__ import annotations

import json
import logging
import re

from json_repair import repair_json

from backend.app.document.models import BBox, ExtractedBlock, ExtractedPage

logger = logging.getLogger(__name__)


def clean_response(raw: str) -> dict:
    """Usuwa markdown fences z odpowiedzi Vision i parsuje JSON.

    Jeśli JSON jest złamany, używa `json_repair` jako fallback.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError as exc:
        logger.warning("[json_repair] Broken JSON (%s) — próbuję naprawić...", exc)
        fixed = repair_json(text)
        result = json.loads(fixed)
        logger.warning("[json_repair] Naprawa udana. Fragment: %r", text[:200])
        return result


def build_section_hint(page: ExtractedPage) -> str:
    """Buduje user_prompt z informacją o nagłówkach sekcji na stronie."""
    sections = page.sections
    if not sections:
        return (
            "This page has 0 section-headings. "
            "element_type 'section-header' must NOT appear in your output."
        )
    if len(sections) == 1:
        return (
            f'This page has exactly 1 section-heading: "{sections[0]}". '
            f"element_type 'section-header' must appear exactly once, "
            f"for this text only."
        )
    items = "\n".join(f'  {i + 1}. "{s}"' for i, s in enumerate(sections))
    return (
        f"This page has exactly {len(sections)} section-headings:\n{items}\n"
        f"element_type 'section-header' must appear exactly {len(sections)} times — "
        "once for each heading above, and for no other elements."
    )


def infer_heading_level(element_type: str) -> int | None:
    if element_type == "section-header":
        return 1
    if element_type == "subsection-header":
        return 2
    return None


def normalize_heading_whitespace(text: str) -> str:
    """Zwija dowolne whitespace (w tym `\\n`, tab, wielokrotne spacje) do
    pojedynczej spacji i trimuje brzegi. Idempotentne."""
    return " ".join(text.split())


def normalize_heading_texts(page: ExtractedPage) -> int:
    """Sanityzuje in-place `text` bloków z heading_level ∈ {1, 2}.

    Rozwiązuje przypadek, gdy Vision zwraca nagłówek z wewnętrznym `\\n`
    (odwzorowaniem line-breaku wizualnego w PDF), co psuje dopasowanie do
    page.sections w reclassify/promote oraz czytelność prefiksu chunka.
    Zwraca liczbę zmodyfikowanych bloków.
    """
    changed = 0
    for b in page.blocks:
        if b.heading_level not in (1, 2):
            continue
        new_text = normalize_heading_whitespace(b.text)
        if new_text != b.text:
            b.text = new_text
            changed += 1
    return changed


def vision_elements_to_blocks(
    page_num: int, elements: list[dict]
) -> list[ExtractedBlock]:
    """Konwertuje surowy JSON z Vision na listę ExtractedBlock."""
    blocks = []
    for idx, elem in enumerate(elements):
        block = ExtractedBlock(
            block_id=f"p{page_num}_b{idx}",
            page=page_num,
            element_type=elem["element_type"],
            text=elem["text"],
            bbox=BBox(x0=0, y0=0, x1=0, y1=0),
            heading_level=infer_heading_level(elem["element_type"]),
        )
        blocks.append(block)
    return blocks


SECTION_PREFIX_RE = re.compile(r"^\d+\.\s+")


def reclassify_spurious_section_headers(page: ExtractedPage) -> int:
    """Reklasyfikuje 'section-header' → 'subsection-header' gdy tekst (po zdjęciu
    prefiksu 'N. ') nie znajduje się w page.sections (TOC jako źródło prawdy).

    Modyfikuje page.blocks in-place. Zwraca liczbę reklasyfikowanych bloków.
    """
    expected = {
        normalize_heading_whitespace(SECTION_PREFIX_RE.sub("", s, count=1))
        for s in page.sections
    }
    changed = 0
    for b in page.blocks:
        if b.element_type != "section-header":
            continue
        stripped = normalize_heading_whitespace(
            SECTION_PREFIX_RE.sub("", b.text, count=1)
        )
        if stripped not in expected:
            b.element_type = "subsection-header"
            b.heading_level = 2
            changed += 1
    return changed


def promote_matching_subsection_headers(page: ExtractedPage) -> int:
    """Promuje 'subsection-header' → 'section-header' gdy tekst (po zdjęciu
    prefiksu 'N. ') pokrywa się z którymkolwiek tytułem w page.sections
    (również znormalizowanym). Operacja symetryczna do
    reclassify_spurious_section_headers.

    Modyfikuje page.blocks in-place. Zwraca liczbę promowanych bloków.
    """
    expected = {
        normalize_heading_whitespace(SECTION_PREFIX_RE.sub("", s, count=1))
        for s in page.sections
    }
    if not expected:
        return 0
    changed = 0
    for b in page.blocks:
        if b.element_type != "subsection-header":
            continue
        stripped = normalize_heading_whitespace(
            SECTION_PREFIX_RE.sub("", b.text, count=1)
        )
        if stripped in expected:
            b.element_type = "section-header"
            b.heading_level = 1
            changed += 1
    return changed
