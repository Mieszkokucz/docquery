"""Testy strukturalne vision extractor.

Sprawdzają to, czego naive nie potrafi — rozpoznawanie typów elementów.
Operują TYLKO na cache (data/extraction/I-X.json), bez API calls.

Jak dodać nowy test: pamiętaj że testy parametryzowane po CHAPTER_IDS
skipują rozdział jeśli cache nie istnieje (fixture `_load_chapter`).
"""

import pytest

from backend.app.config import VISION_CACHE_DIR
from backend.app.document.models import ExtractedChapter
from backend.app.document.vision_response import (
    SECTION_PREFIX_RE,
    reclassify_spurious_section_headers,
)

CHAPTER_IDS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


def _load_chapter(chapter_id: str) -> ExtractedChapter:
    path = VISION_CACHE_DIR / f"{chapter_id}.json"
    if not path.exists():
        pytest.skip(f"Brak cache: {path}")
    return ExtractedChapter.load_json(path)


@pytest.mark.parametrize("chapter_id", CHAPTER_IDS)
def test_every_nontitle_page_has_blocks(chapter_id):
    ch = _load_chapter(chapter_id)
    for p in ch.pages[1:]:
        assert p.blocks, f"{chapter_id} strona {p.page_num} nie ma bloków"


@pytest.mark.parametrize("chapter_id", CHAPTER_IDS)
def test_chapter_has_section_header(chapter_id):
    ch = _load_chapter(chapter_id)
    headers = ch.get_blocks_by_type("section-header")
    assert len(headers) >= 1, f"{chapter_id} nie zawiera żadnego section-header"


@pytest.mark.parametrize("chapter_id", CHAPTER_IDS)
def test_heading_levels_consistent(chapter_id):
    ch = _load_chapter(chapter_id)
    for b in ch.get_all_blocks():
        if b.element_type == "section-header":
            assert b.heading_level == 1, (
                f"{chapter_id} p{b.page} section-header level={b.heading_level}"
            )
        elif b.element_type == "subsection-header":
            assert b.heading_level == 2, (
                f"{chapter_id} p{b.page} subsection-header level={b.heading_level}"
            )


@pytest.mark.parametrize("chapter_id", CHAPTER_IDS)
def test_infographic_have_descriptions(chapter_id):
    """Vision prompt wymaga opisu po polsku dla każdego `infographic`."""
    ch = _load_chapter(chapter_id)
    for b in ch.get_blocks_by_type("infographic"):
        assert b.text.strip(), f"{chapter_id} p{b.page} infographic bez opisu"


def test_tables_detected_in_document():
    """Przewaga Vision: rozpoznaje tabele jako osobny typ bloku.
    Naive (PyMuPDF text mode) zwraca tabele jako płaski tekst.
    """
    total_tables = sum(
        len(_load_chapter(cid).get_blocks_by_type("table")) for cid in CHAPTER_IDS
    )
    assert total_tables > 0, "Żaden rozdział nie zawiera bloków typu 'table'"


def test_list_prezesa_is_section_header():
    """Konkretny sanity check: 'List Prezesa Zarządu' na stronie 4 to section-header."""
    ch = _load_chapter("I")
    p4 = next((p for p in ch.pages if p.page_num == 4), None)
    assert p4 is not None, "Rozdział I nie zawiera strony 4"
    headers = [b for b in p4.blocks if b.element_type == "section-header"]
    assert any("List Prezesa" in h.text for h in headers), (
        f"Strona 4 section-headers: {[h.text for h in headers]}"
    )


@pytest.mark.parametrize("chapter_id", CHAPTER_IDS)
def test_block_ids_unique_within_page(chapter_id):
    """block_id jest unikalny w obrębie strony (format 'p<num>_b<idx>')."""
    ch = _load_chapter(chapter_id)
    for p in ch.pages:
        ids = [b.block_id for b in p.blocks]
        assert len(ids) == len(set(ids)), f"{chapter_id} p{p.page_num} duplikaty: {ids}"


@pytest.mark.parametrize("chapter_id", CHAPTER_IDS)
def test_section_headers_match_toc_after_postprocess(chapter_id):
    """Po postprocess zestaw section-headers na stronie (po zdjęciu prefiksu
    numerycznego) == page.sections z TOC.
    Postprocess aplikowany w locie — nie modyfikuje cache na dysku.
    """
    ch = _load_chapter(chapter_id)
    for page in ch.pages:
        extracted = [
            SECTION_PREFIX_RE.sub("", b.text, count=1).strip()
            for b in page.blocks
            if b.element_type == "section-header"
        ]
        expected = [
            SECTION_PREFIX_RE.sub("", s, count=1).strip() for s in page.sections
        ]
        assert extracted == expected, (
            f"{chapter_id} p{page.page_num}: TOC={expected}, VISION={extracted}"
        )


@pytest.mark.parametrize("chapter_id", CHAPTER_IDS)
def test_block_page_matches_parent(chapter_id):
    """Każdy block.page = page_num rodzica (spójność serializacji)."""
    ch = _load_chapter(chapter_id)
    for p in ch.pages:
        for b in p.blocks:
            assert b.page == p.page_num, (
                f"{chapter_id} {b.block_id} page={b.page}, rodzic={p.page_num}"
            )
