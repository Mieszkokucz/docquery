"""Parsing odpowiedzi Claude Vision — JSON → ExtractedBlock."""

from __future__ import annotations

import json
import logging

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
