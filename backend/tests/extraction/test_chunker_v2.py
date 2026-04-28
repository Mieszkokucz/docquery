"""Unit testy dla chunker_v2.py — tabele/obrazy nie tną chunka tekstowego."""

from __future__ import annotations

from backend.app.document.models import (
    BBox,
    DocumentMetadata,
    ExtractedBlock,
    ExtractedChapter,
    ExtractedDocument,
    ExtractedPage,
)
from backend.app.document.chunker_v2 import chunk_document


def _block(idx: int, page: int, element_type: str, text: str) -> ExtractedBlock:
    return ExtractedBlock(
        block_id=f"p{page}_b{idx}",
        page=page,
        element_type=element_type,
        text=text,
        bbox=BBox(0, 0, 0, 0),
    )


def _doc(
    pages: list[ExtractedPage], chapter_title: str = "Rozdział I"
) -> ExtractedDocument:
    for p in pages:
        if p.chapter is None:
            p.chapter = chapter_title
    chapter = ExtractedChapter(
        chapter_id="I",
        title=chapter_title,
        page_start=pages[0].page_num,
        page_end=pages[-1].page_num,
        pages=pages,
    )
    return ExtractedDocument(
        metadata=DocumentMetadata(
            source_file="test.pdf", total_pages=len(pages), extraction_date="2026-04-19"
        ),
        title="Test",
        chapters=[chapter],
    )


# --- Podstawowy przypadek: tabela nie przerywa buffora ---


def test_table_between_text_merges_surrounding_text():
    """Tekst A → tabela → tekst B (ta sama strona, ta sama sekcja)
    → 2 chunki: tabela + jeden scalony text z A i B."""
    page = ExtractedPage(
        page_num=10,
        sections=[],
        blocks=[
            _block(0, 10, "text", "Fragment A."),
            _block(1, 10, "table", "| kol1 | kol2 |\n| 1 | 2 |"),
            _block(2, 10, "text", "Fragment B."),
        ],
    )
    chunks = chunk_document(_doc([page]), max_chars=10_000)

    types = [c["element_type"] for c in chunks]
    assert types.count("table") == 1
    assert types.count("text") == 1

    text_chunk = next(c for c in chunks if c["element_type"] == "text")
    assert "Fragment A." in text_chunk["search_text"]
    assert "Fragment B." in text_chunk["search_text"]
    # Treść tabeli NIE trafia do text chunka
    assert "kol1" not in text_chunk["search_text"]


def test_infographic_also_does_not_cut_text():
    page = ExtractedPage(
        page_num=5,
        blocks=[
            _block(0, 5, "text", "Przed infografiką."),
            _block(1, 5, "infographic", "Opis infografiki"),
            _block(2, 5, "text", "Po infografice."),
        ],
    )
    chunks = chunk_document(_doc([page]))
    text_chunks = [c for c in chunks if c["element_type"] == "text"]
    infographic_chunks = [c for c in chunks if c["element_type"] == "infographic"]
    assert len(text_chunks) == 1
    assert len(infographic_chunks) == 1
    assert "Przed infografiką." in text_chunks[0]["search_text"]
    assert "Po infografice." in text_chunks[0]["search_text"]


def test_text_table_text_infographic_text_merges_all_text():
    """T → tabela → T → infografika → T → 3 chunki: 1 text scalony + 2 media."""
    page = ExtractedPage(
        page_num=20,
        blocks=[
            _block(0, 20, "text", "Część 1."),
            _block(1, 20, "table", "tabela"),
            _block(2, 20, "text", "Część 2."),
            _block(3, 20, "infographic", "wykres"),
            _block(4, 20, "text", "Część 3."),
        ],
    )
    chunks = chunk_document(_doc([page]), max_chars=10_000)

    types = [c["element_type"] for c in chunks]
    assert types.count("table") == 1
    assert types.count("infographic") == 1
    text_chunks = [c for c in chunks if c["element_type"] == "text"]
    assert len(text_chunks) == 1
    t = text_chunks[0]["search_text"]
    assert "Część 1." in t and "Część 2." in t and "Część 3." in t


def test_picture_is_skipped_and_does_not_cut_text():
    """`picture` należy do SKIP — nie tworzy chunka i nie przerywa tekstu."""
    page = ExtractedPage(
        page_num=7,
        blocks=[
            _block(0, 7, "text", "Przed logo."),
            _block(1, 7, "picture", "Logo XYZ"),
            _block(2, 7, "text", "Po logo."),
        ],
    )
    chunks = chunk_document(_doc([page]))
    types = [c["element_type"] for c in chunks]
    assert "picture" not in types
    text_chunks = [c for c in chunks if c["element_type"] == "text"]
    assert len(text_chunks) == 1
    joined = text_chunks[0]["search_text"]
    assert "Przed logo." in joined
    assert "Po logo." in joined
    assert "Logo XYZ" not in joined


def test_footnote_accumulates_in_text_chunk():
    """`footnote` NIE jest pomijany w v2 — trafia do chunka tekstowego."""
    page = ExtractedPage(
        page_num=8,
        blocks=[
            _block(0, 8, "text", "Akapit."),
            _block(1, 8, "footnote", "[1] Treść przypisu."),
        ],
    )
    chunks = chunk_document(_doc([page]))
    text_chunks = [c for c in chunks if c["element_type"] == "text"]
    assert len(text_chunks) == 1
    joined = text_chunks[0]["content"]
    assert "Akapit." in joined
    assert "[1] Treść przypisu." in joined


def test_identifier_accumulates_in_text_chunk():
    """`identifier` (GRI/TCFD/SDG) to zwykły blok tekstowy — nie medium, nie SKIP."""
    page = ExtractedPage(
        page_num=9,
        blocks=[
            _block(0, 9, "text", "Przed identyfikatorem."),
            _block(1, 9, "identifier", "GRI 302-1"),
            _block(2, 9, "text", "Po identyfikatorze."),
        ],
    )
    chunks = chunk_document(_doc([page]))
    text_chunks = [c for c in chunks if c["element_type"] == "text"]
    assert len(text_chunks) == 1
    joined = text_chunks[0]["content"]
    assert "Przed identyfikatorem." in joined
    assert "GRI 302-1" in joined
    assert "Po identyfikatorze." in joined


def test_caption_prefixes_infographic_content():
    """Caption bezpośrednio nad infografiką → prefiks `content` chunka typu
    `infographic`, analogicznie do tabeli."""
    page = ExtractedPage(
        page_num=11,
        blocks=[
            _block(0, 11, "text", "Wstęp."),
            _block(1, 11, "caption", "Wykres 2. Udział rynkowy"),
            _block(2, 11, "infographic", "Wykres słupkowy 2022–2025..."),
        ],
    )
    chunks = chunk_document(_doc([page]))
    infographic = next(c for c in chunks if c["element_type"] == "infographic")
    assert infographic["content"].startswith("Wykres 2. Udział rynkowy")
    assert "Wykres słupkowy 2022–2025..." in infographic["content"]
    text_chunks = [c for c in chunks if c["element_type"] == "text"]
    assert len(text_chunks) == 1
    assert "Wykres 2. Udział rynkowy" not in text_chunks[0]["content"]


# --- Section-header NADAL przerywa ---


def test_section_header_still_cuts_even_around_media():
    page = ExtractedPage(
        page_num=30,
        sections=["Sekcja A", "Sekcja B"],
        blocks=[
            _block(0, 30, "section-header", "Sekcja A"),
            _block(1, 30, "text", "Tekst sekcji A."),
            _block(2, 30, "section-header", "Sekcja B"),
            _block(3, 30, "table", "tabela"),
            _block(4, 30, "text", "Tekst sekcji B."),
        ],
    )
    chunks = chunk_document(_doc([page]))

    text_chunks = [c for c in chunks if c["element_type"] == "text"]
    assert len(text_chunks) == 2
    assert text_chunks[0]["section"] == "Sekcja A"
    assert "Tekst sekcji A." in text_chunks[0]["search_text"]
    assert text_chunks[1]["section"] == "Sekcja B"
    assert "Tekst sekcji B." in text_chunks[1]["search_text"]

    table_chunk = next(c for c in chunks if c["element_type"] == "table")
    assert table_chunk["section"] == "Sekcja B"


# --- Caption poprzedzający tabelę ---


def test_caption_goes_into_media_not_into_text_buffer():
    page = ExtractedPage(
        page_num=40,
        blocks=[
            _block(0, 40, "text", "Wstęp."),
            _block(1, 40, "caption", "Tabela 1. Statystyki"),
            _block(2, 40, "table", "dane"),
            _block(3, 40, "text", "Podsumowanie."),
        ],
    )
    chunks = chunk_document(_doc([page]))

    table_chunk = next(c for c in chunks if c["element_type"] == "table")
    assert "Tabela 1. Statystyki" in table_chunk["search_text"]
    assert "dane" in table_chunk["search_text"]

    text_chunks = [c for c in chunks if c["element_type"] == "text"]
    assert len(text_chunks) == 1
    joined = text_chunks[0]["search_text"]
    assert "Wstęp." in joined
    assert "Podsumowanie." in joined
    assert "Tabela 1. Statystyki" not in joined


# --- max_chars dalej działa dla samych bloków tekstowych ---


def test_max_chars_splits_long_text_but_preserves_media_semantics():
    long_a = "A" * 400
    long_b = "B" * 400
    long_c = "C" * 400
    page = ExtractedPage(
        page_num=50,
        blocks=[
            _block(0, 50, "text", long_a),
            _block(1, 50, "text", long_b),
            _block(2, 50, "table", "T"),
            _block(3, 50, "text", long_c),
        ],
    )
    chunks = chunk_document(_doc([page]), max_chars=500)

    text_chunks = [c for c in chunks if c["element_type"] == "text"]
    # long_a nie mieści się z long_b w jednym chunku → split po A;
    # po tabeli buffer trzyma long_b, dokleja long_c → drugi split.
    assert len(text_chunks) >= 2
    for tc in text_chunks:
        assert "T" not in tc["search_text"]  # tabela w osobnym chunku

    assert sum(1 for c in chunks if c["element_type"] == "table") == 1


# --- Rozdział search_text vs content ---


def test_search_text_has_prefix_content_is_raw():
    """search_text ma prefiks `chapter > section` i `Strony:`; content jest surowy."""
    page1 = ExtractedPage(
        page_num=60,
        sections=["Sekcja X"],
        blocks=[
            _block(0, 60, "section-header", "Sekcja X"),
            _block(1, 60, "text", "Treść jeden."),
            _block(2, 60, "caption", "Tabela 7. Opis"),
            _block(3, 60, "table", "wartości"),
        ],
    )
    page2 = ExtractedPage(
        page_num=61,
        blocks=[
            _block(0, 61, "text", "Treść dwa."),
        ],
    )
    chunks = chunk_document(_doc([page1, page2]), max_chars=10_000)

    text_chunk = next(c for c in chunks if c["element_type"] == "text")
    # search_text zawiera prefiks i rozpiętość stron
    assert "Rozdział I > Sekcja X" in text_chunk["search_text"]
    assert "Strony:" in text_chunk["search_text"]
    assert "Treść jeden." in text_chunk["search_text"]
    assert "Treść dwa." in text_chunk["search_text"]
    # content: tylko surowe bloki
    assert text_chunk["content"] == "Treść jeden.\n\nTreść dwa."
    assert " > " not in text_chunk["content"]
    assert "Strony:" not in text_chunk["content"]

    table_chunk = next(c for c in chunks if c["element_type"] == "table")
    assert "Rozdział I > Sekcja X" in table_chunk["search_text"]
    assert table_chunk["content"] == "Tabela 7. Opis\n\nwartości"
    assert " > " not in table_chunk["content"]
