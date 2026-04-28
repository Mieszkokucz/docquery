"""Unit testy dla structure_extractor.

Operują na prawdziwym raport_2024_pl.pdf (deterministyczne — PDF się nie zmienia).
Test skipuje jeśli pełny PDF nie istnieje (fixture full_pdf_path w conftest.py).
"""

from backend.app.document.structure_extractor import extract_structure

EXPECTED_CHAPTER_IDS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


def test_extract_structure_returns_10_chapters(full_pdf_path):
    document, doc = extract_structure(full_pdf_path)
    doc.close()
    assert len(document.chapters) == 10
    assert [ch.chapter_id for ch in document.chapters] == EXPECTED_CHAPTER_IDS


def test_extract_title_contains_year_and_report(full_pdf_path):
    document, doc = extract_structure(full_pdf_path)
    doc.close()
    assert "2024" in document.title
    upper = document.title.upper()
    assert "RAPORT" in upper or "SPRAWOZDANIE" in upper


def test_chapter_ranges_contiguous(full_pdf_path):
    """page_end rozdziału N + 1 = page_start rozdziału N+1 (brak luk w TOC)."""
    document, doc = extract_structure(full_pdf_path)
    doc.close()
    for prev, curr in zip(document.chapters, document.chapters[1:]):
        assert prev.page_end + 1 == curr.page_start, (
            f"Luka między {prev.chapter_id}(page_end={prev.page_end}) "
            f"i {curr.chapter_id}(page_start={curr.page_start})"
        )


def test_chapter_ranges_ordered(full_pdf_path):
    """page_start < page_end dla każdego rozdziału, brak rozdziałów zerowych."""
    document, doc = extract_structure(full_pdf_path)
    doc.close()
    for ch in document.chapters:
        assert ch.page_start <= ch.page_end, (
            f"{ch.chapter_id}: {ch.page_start} > {ch.page_end}"
        )


def test_every_chapter_has_pages(full_pdf_path):
    """Każdy rozdział ma wypełnioną listę pages zgodnie z zakresem (przed Vision)."""
    document, doc = extract_structure(full_pdf_path)
    doc.close()
    for ch in document.chapters:
        expected_count = ch.page_end - ch.page_start + 1
        assert len(ch.pages) == expected_count, (
            f"{ch.chapter_id}: {len(ch.pages)} pages, spodziewane {expected_count}"
        )


def test_pages_have_content_rect(full_pdf_path):
    """Non-title page ma content_rect po _populate_content_rects."""
    document, doc = extract_structure(full_pdf_path)
    doc.close()
    for ch in document.chapters:
        for p in ch.pages[1:]:
            assert p.content_rect is not None, (
                f"{ch.chapter_id} strona {p.page_num} bez content_rect"
            )


def test_metadata_populated(full_pdf_path):
    document, doc = extract_structure(full_pdf_path)
    doc.close()
    assert document.metadata.source_file
    assert document.metadata.total_pages > 0
    assert document.metadata.extraction_date
