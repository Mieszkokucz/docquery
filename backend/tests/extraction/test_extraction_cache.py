"""Unit testy dla extraction_cache.py — I/O per rozdział + sprawdzenie kompletności."""

from backend.app.document.extraction_cache import (
    chapter_cache_path,
    chapter_is_complete,
    load_cached_chapters,
)
from backend.app.document.models import (
    BBox,
    DocumentMetadata,
    ExtractedBlock,
    ExtractedChapter,
    ExtractedDocument,
    ExtractedPage,
)


def _make_block(text: str = "x") -> ExtractedBlock:
    return ExtractedBlock(
        block_id="p1_b0",
        page=1,
        element_type="text",
        text=text,
        bbox=BBox(0, 0, 0, 0),
    )


def _make_chapter(chapter_id: str, pages: list[ExtractedPage]) -> ExtractedChapter:
    return ExtractedChapter(
        chapter_id=chapter_id,
        title=f"{chapter_id} Test",
        page_start=pages[0].page_num if pages else 1,
        page_end=pages[-1].page_num if pages else 1,
        pages=pages,
    )


# --- chapter_cache_path ---


def test_chapter_cache_path(tmp_path):
    assert chapter_cache_path(tmp_path, "III") == tmp_path / "III.json"


def test_chapter_cache_path_custom_dir(tmp_path):
    sub = tmp_path / "nested"
    assert chapter_cache_path(sub, "X") == sub / "X.json"


# --- chapter_is_complete ---


def test_chapter_is_complete_all_nontitle_pages_have_blocks():
    ch = _make_chapter(
        "A",
        [
            ExtractedPage(page_num=1),  # title page (index 0) — pomijana
            ExtractedPage(page_num=2, blocks=[_make_block()]),
            ExtractedPage(page_num=3, blocks=[_make_block()]),
        ],
    )
    assert chapter_is_complete(ch) is True


def test_chapter_is_complete_missing_blocks():
    ch = _make_chapter(
        "B",
        [
            ExtractedPage(page_num=1),  # title (OK)
            ExtractedPage(page_num=2, blocks=[_make_block()]),
            ExtractedPage(page_num=3),  # non-title, bez bloków — PROBLEM
        ],
    )
    assert chapter_is_complete(ch) is False


def test_chapter_is_complete_title_page_empty_ok():
    """Strona 0 (title) może być pusta — tylko non-title muszą mieć bloki."""
    ch = _make_chapter(
        "C",
        [
            ExtractedPage(page_num=1),  # title, pusta — OK
            ExtractedPage(page_num=2, blocks=[_make_block()]),
        ],
    )
    assert chapter_is_complete(ch) is True


def test_chapter_is_complete_single_page_only_title():
    """Rozdział z 1 stroną (tylko title) → brak non-title → vacuously True."""
    ch = _make_chapter("D", [ExtractedPage(page_num=1)])
    assert chapter_is_complete(ch) is True


# --- load_cached_chapters ---


def test_load_cached_chapters_populates_in_place(tmp_path):
    """load_cached_chapters wczytuje pages z cache do istniejącego document in-place."""
    # 1. Przygotuj document z pustymi chapters (jak po extract_structure)
    document = ExtractedDocument(
        metadata=DocumentMetadata(source_file="x", total_pages=5, extraction_date="d"),
        title="Test",
        chapters=[
            _make_chapter("I", [ExtractedPage(page_num=1), ExtractedPage(page_num=2)]),
            _make_chapter("II", [ExtractedPage(page_num=3)]),
        ],
    )

    # 2. Zapisz cache tylko dla "I"
    cached_I = _make_chapter(
        "I",
        [
            ExtractedPage(page_num=1),
            ExtractedPage(page_num=2, blocks=[_make_block("cached")]),
        ],
    )
    cached_I.save_json(chapter_cache_path(tmp_path, "I"))

    # 3. Wczytaj
    load_cached_chapters(document, tmp_path)

    # 4. Rozdział I ma bloki z cache; II pozostał niezmieniony
    assert document.chapters[0].pages[1].blocks[0].text == "cached"
    assert document.chapters[1].pages[0].blocks == []


def test_load_cached_chapters_skips_missing(tmp_path):
    """Jeśli cache nie istnieje, rozdział pozostaje bez zmian."""
    document = ExtractedDocument(
        metadata=DocumentMetadata(source_file="x", total_pages=1, extraction_date="d"),
        title="Test",
        chapters=[_make_chapter("Z", [ExtractedPage(page_num=1)])],
    )
    load_cached_chapters(document, tmp_path)  # tmp_path jest puste
    assert document.chapters[0].pages[0].blocks == []


# --- round-trip save/load ---


def test_chapter_json_roundtrip(tmp_path):
    """ExtractedChapter.save_json → load_json zwraca equivalent obiektu."""
    original = _make_chapter(
        "I",
        [
            ExtractedPage(page_num=1, sections=["s1"]),
            ExtractedPage(
                page_num=2,
                content_rect=BBox(10.0, 20.0, 30.0, 40.0),
                chapter="I Test",
                blocks=[
                    ExtractedBlock(
                        block_id="p2_b0",
                        page=2,
                        element_type="section-header",
                        text="Tytuł",
                        bbox=BBox(1.0, 2.0, 3.0, 4.0),
                        heading_level=1,
                    ),
                ],
            ),
        ],
    )
    path = tmp_path / "I.json"
    original.save_json(path)
    loaded = ExtractedChapter.load_json(path)

    assert loaded.chapter_id == original.chapter_id
    assert len(loaded.pages) == 2
    assert loaded.pages[1].content_rect.x0 == 10.0
    assert loaded.pages[1].blocks[0].heading_level == 1
    assert loaded.pages[1].blocks[0].text == "Tytuł"
