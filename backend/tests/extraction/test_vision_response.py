"""Unit testy dla vision_response.py — parsery JSON, bez I/O."""

import pytest

from backend.app.document.models import BBox, ExtractedBlock, ExtractedPage
from backend.app.document.vision_response import (
    build_section_hint,
    clean_response,
    infer_heading_level,
    normalize_heading_texts,
    normalize_heading_whitespace,
    promote_matching_subsection_headers,
    reclassify_spurious_section_headers,
    vision_elements_to_blocks,
)

# --- clean_response ---


def test_clean_response_valid_json():
    raw = '{"elements": [{"element_type": "text", "text": "hello"}]}'
    assert clean_response(raw) == {
        "elements": [{"element_type": "text", "text": "hello"}]
    }


def test_clean_response_with_markdown_fence():
    raw = '```json\n{"elements": []}\n```'
    assert clean_response(raw) == {"elements": []}


def test_clean_response_with_generic_fence():
    raw = '```\n{"elements": []}\n```'
    assert clean_response(raw) == {"elements": []}


def test_clean_response_broken_json_repaired():
    """Trailing comma → json_repair naprawia."""
    raw = '{"elements": [{"element_type": "text", "text": "a",}]}'
    result = clean_response(raw)
    assert "elements" in result
    assert result["elements"][0]["text"] == "a"


def test_clean_response_completely_broken_raises():
    """Zupełnie zepsuty input — json_repair może zwrócić częściowy wynik."""
    # json_repair jest tolerancyjny — ten test sprawdza że nie wybucha
    result = clean_response('{"elements": [broken')
    assert isinstance(result, dict)


# --- build_section_hint ---


def test_build_section_hint_no_sections():
    page = ExtractedPage(page_num=5, sections=[])
    hint = build_section_hint(page)
    assert "0 section-headings" in hint
    assert "must NOT appear" in hint


def test_build_section_hint_one_section():
    page = ExtractedPage(page_num=3, sections=["List Prezesa Zarządu"])
    hint = build_section_hint(page)
    assert "exactly 1" in hint
    assert "List Prezesa Zarządu" in hint


def test_build_section_hint_multiple_sections():
    page = ExtractedPage(page_num=7, sections=["A", "B", "C"])
    hint = build_section_hint(page)
    assert "exactly 3" in hint
    assert '"A"' in hint and '"B"' in hint and '"C"' in hint


# --- infer_heading_level ---


@pytest.mark.parametrize(
    "element_type,expected",
    [
        ("section-header", 1),
        ("subsection-header", 2),
        ("text", None),
        ("table", None),
        ("picture", None),
        ("list", None),
        ("caption", None),
        ("footnote", None),
        ("other", None),
    ],
)
def test_infer_heading_level(element_type, expected):
    assert infer_heading_level(element_type) == expected


# --- vision_elements_to_blocks ---


def test_vision_elements_to_blocks_empty():
    assert vision_elements_to_blocks(page_num=1, elements=[]) == []


def test_vision_elements_to_blocks_assigns_unique_block_ids():
    elements = [
        {"element_type": "text", "text": "a"},
        {"element_type": "text", "text": "b"},
        {"element_type": "text", "text": "c"},
    ]
    blocks = vision_elements_to_blocks(page_num=5, elements=elements)
    assert [b.block_id for b in blocks] == ["p5_b0", "p5_b1", "p5_b2"]


def test_vision_elements_to_blocks_preserves_page_and_text():
    blocks = vision_elements_to_blocks(
        7, [{"element_type": "text", "text": "hello world"}]
    )
    assert blocks[0].page == 7
    assert blocks[0].text == "hello world"


def test_vision_elements_section_header_heading_level_1():
    blocks = vision_elements_to_blocks(
        1, [{"element_type": "section-header", "text": "Title"}]
    )
    assert blocks[0].heading_level == 1


def test_vision_elements_subsection_header_heading_level_2():
    blocks = vision_elements_to_blocks(
        1, [{"element_type": "subsection-header", "text": "Subtitle"}]
    )
    assert blocks[0].heading_level == 2


def test_vision_elements_text_heading_level_none():
    blocks = vision_elements_to_blocks(
        1, [{"element_type": "text", "text": "paragraph"}]
    )
    assert blocks[0].heading_level is None


def test_vision_elements_bbox_is_placeholder():
    """Vision nie zwraca bbox — zawsze (0,0,0,0) w blokach."""
    blocks = vision_elements_to_blocks(
        1, [{"element_type": "text", "text": "x"}]
    )
    b = blocks[0].bbox
    assert (b.x0, b.y0, b.x1, b.y1) == (0, 0, 0, 0)


# --- reclassify_spurious_section_headers ---


def _make_block(
    idx: int, page_num: int, element_type: str, text: str
) -> ExtractedBlock:
    level = infer_heading_level(element_type)
    return ExtractedBlock(
        block_id=f"p{page_num}_b{idx}",
        page=page_num,
        element_type=element_type,
        text=text,
        bbox=BBox(0, 0, 0, 0),
        heading_level=level,
    )


def test_reclassify_keeps_matching_header():
    page = ExtractedPage(page_num=49, sections=["Nasi interesariusze"])
    page.blocks = [_make_block(0, 49, "section-header", "2. Nasi interesariusze")]
    changed = reclassify_spurious_section_headers(page)
    assert changed == 0
    assert page.blocks[0].element_type == "section-header"
    assert page.blocks[0].heading_level == 1


def test_reclassify_keeps_matching_header_when_sections_have_numeric_prefix():
    """Konwencja produkcyjna: _parse_toc zapisuje sections z prefiksem 'N. '."""
    page = ExtractedPage(
        page_num=15, sections=["1. Strategia, czyli co nas wyróżnia"]
    )
    page.blocks = [
        _make_block(0, 15, "section-header", "1. Strategia, czyli co nas wyróżnia")
    ]
    changed = reclassify_spurious_section_headers(page)
    assert changed == 0
    assert page.blocks[0].element_type == "section-header"
    assert page.blocks[0].heading_level == 1


def test_reclassify_converts_spurious_header():
    page = ExtractedPage(page_num=49, sections=["Nasi interesariusze"])
    page.blocks = [
        _make_block(0, 49, "section-header", "Rynek pracy pozostaje stabilny")
    ]
    changed = reclassify_spurious_section_headers(page)
    assert changed == 1
    assert page.blocks[0].element_type == "subsection-header"
    assert page.blocks[0].heading_level == 2


def test_reclassify_mixed_blocks():
    page = ExtractedPage(page_num=49, sections=["Nasi interesariusze"])
    page.blocks = [
        _make_block(0, 49, "section-header", "Rynek pracy pozostaje stabilny"),
        _make_block(1, 49, "section-header", "2. Nasi interesariusze"),
    ]
    changed = reclassify_spurious_section_headers(page)
    assert changed == 1
    assert page.blocks[0].element_type == "subsection-header"
    assert page.blocks[1].element_type == "section-header"


def test_reclassify_ignores_non_section_blocks():
    page = ExtractedPage(page_num=49, sections=["Nasi interesariusze"])
    page.blocks = [
        _make_block(0, 49, "text", "zwykły paragraf"),
        _make_block(1, 49, "subsection-header", "Jakiś podnagłówek"),
    ]
    changed = reclassify_spurious_section_headers(page)
    assert changed == 0
    assert page.blocks[0].element_type == "text"
    assert page.blocks[1].element_type == "subsection-header"


def test_reclassify_preserves_block_order_and_identity():
    """Inwariant: postprocess zmienia TYLKO element_type i heading_level.
    Kolejność, block_id, text, page, bbox — bez zmian.
    """
    page = ExtractedPage(page_num=49, sections=["Nasi interesariusze"])
    page.blocks = [
        _make_block(0, 49, "text", "akapit pierwszy"),
        _make_block(1, 49, "section-header", "Rynek pracy pozostaje stabilny"),
        _make_block(2, 49, "text", "akapit drugi"),
        _make_block(3, 49, "section-header", "2. Nasi interesariusze"),
        _make_block(4, 49, "picture", "opis obrazka"),
    ]
    snapshot_before = [
        (b.block_id, b.text, b.page, (b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1))
        for b in page.blocks
    ]
    original_types = [b.element_type for b in page.blocks]

    reclassify_spurious_section_headers(page)

    snapshot_after = [
        (b.block_id, b.text, b.page, (b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1))
        for b in page.blocks
    ]
    assert snapshot_after == snapshot_before, "Postprocess zmienił tożsamość bloków"
    assert len(page.blocks) == len(snapshot_before), "Liczba bloków się zmieniła"

    new_types = [b.element_type for b in page.blocks]
    assert new_types == [
        "text",
        "subsection-header",
        "text",
        "section-header",
        "picture",
    ]
    for i, (old, new) in enumerate(zip(original_types, new_types)):
        if old == new:
            continue
        assert old == "section-header" and new == "subsection-header", (
            f"blok {i}: nieoczekiwana zmiana {old} → {new}"
        )


def test_reclassify_numeric_prefix_but_not_in_toc():
    """Nawet z prefiksem 'N. ', jeśli tekst (po zdjęciu) nie jest w TOC → subsection."""
    page = ExtractedPage(page_num=10, sections=["Inne"])
    page.blocks = [_make_block(0, 10, "section-header", "5. Coś tam")]
    changed = reclassify_spurious_section_headers(page)
    assert changed == 1
    assert page.blocks[0].element_type == "subsection-header"
    assert page.blocks[0].heading_level == 2


# --- promote_matching_subsection_headers ---


def test_promote_matching_subsection_to_section():
    page = ExtractedPage(
        page_num=15, sections=["1. Strategia, czyli co nas wyróżnia"]
    )
    page.blocks = [
        _make_block(0, 15, "subsection-header", "1. Strategia, czyli co nas wyróżnia")
    ]
    changed = promote_matching_subsection_headers(page)
    assert changed == 1
    assert page.blocks[0].element_type == "section-header"
    assert page.blocks[0].heading_level == 1


def test_promote_handles_prefix_on_one_side_only():
    page = ExtractedPage(page_num=49, sections=["Nasi interesariusze"])
    page.blocks = [
        _make_block(0, 49, "subsection-header", "2. Nasi interesariusze")
    ]
    changed = promote_matching_subsection_headers(page)
    assert changed == 1
    assert page.blocks[0].element_type == "section-header"
    assert page.blocks[0].heading_level == 1


def test_promote_leaves_unrelated_subsections():
    page = ExtractedPage(page_num=49, sections=["Nasi interesariusze"])
    page.blocks = [
        _make_block(0, 49, "subsection-header", "Rynek pracy pozostaje stabilny")
    ]
    changed = promote_matching_subsection_headers(page)
    assert changed == 0
    assert page.blocks[0].element_type == "subsection-header"


def test_promote_ignores_non_subsection_blocks():
    page = ExtractedPage(page_num=15, sections=["1. Strategia"])
    page.blocks = [
        _make_block(0, 15, "text", "1. Strategia"),
        _make_block(1, 15, "section-header", "1. Strategia"),
        _make_block(2, 15, "picture", "1. Strategia"),
    ]
    changed = promote_matching_subsection_headers(page)
    assert changed == 0
    assert page.blocks[0].element_type == "text"
    assert page.blocks[1].element_type == "section-header"
    assert page.blocks[2].element_type == "picture"


def test_promote_empty_sections_noop():
    page = ExtractedPage(page_num=5, sections=[])
    page.blocks = [_make_block(0, 5, "subsection-header", "Cokolwiek")]
    assert promote_matching_subsection_headers(page) == 0


def test_promote_preserves_block_identity():
    page = ExtractedPage(
        page_num=15, sections=["1. Strategia, czyli co nas wyróżnia"]
    )
    page.blocks = [
        _make_block(0, 15, "text", "akapit"),
        _make_block(1, 15, "subsection-header", "1. Strategia, czyli co nas wyróżnia"),
        _make_block(2, 15, "text", "akapit 2"),
    ]
    snapshot_before = [
        (b.block_id, b.text, b.page, (b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1))
        for b in page.blocks
    ]
    promote_matching_subsection_headers(page)
    snapshot_after = [
        (b.block_id, b.text, b.page, (b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1))
        for b in page.blocks
    ]
    assert snapshot_after == snapshot_before
    assert [b.element_type for b in page.blocks] == [
        "text", "section-header", "text"
    ]


def test_demote_and_promote_idempotent():
    """Dwukrotny przebieg (demote, promote) nie zmienia już nic drugim razem."""
    page = ExtractedPage(page_num=15, sections=["1. Strategia"])
    page.blocks = [
        _make_block(0, 15, "section-header", "Coś niezgodnego z ToC"),
        _make_block(1, 15, "subsection-header", "1. Strategia"),
    ]
    d1 = reclassify_spurious_section_headers(page)
    p1 = promote_matching_subsection_headers(page)
    assert (d1, p1) == (1, 1)
    d2 = reclassify_spurious_section_headers(page)
    p2 = promote_matching_subsection_headers(page)
    assert (d2, p2) == (0, 0)


# --- normalize_heading_whitespace / normalize_heading_texts ---


def test_normalize_heading_whitespace_collapses_newlines():
    assert normalize_heading_whitespace("Wyniki\nfinansowe") == "Wyniki finansowe"
    assert normalize_heading_whitespace("  a \t b\n\nc  ") == "a b c"
    assert normalize_heading_whitespace("bez zmian") == "bez zmian"


def test_normalize_heading_whitespace_idempotent():
    once = normalize_heading_whitespace("Wyniki\nfinansowe")
    assert normalize_heading_whitespace(once) == once


def test_normalize_heading_texts_only_touches_heading_blocks():
    page = ExtractedPage(page_num=1, sections=[])
    page.blocks = [
        _make_block(0, 1, "section-header", "Wyniki\nfinansowe"),
        _make_block(1, 1, "subsection-header", "Pod\nnagłówek"),
        _make_block(2, 1, "text", "paragraf z\nłamaniem linii"),
        _make_block(3, 1, "list", "- item\n- item 2"),
    ]
    changed = normalize_heading_texts(page)
    assert changed == 2
    assert page.blocks[0].text == "Wyniki finansowe"
    assert page.blocks[1].text == "Pod nagłówek"
    assert page.blocks[2].text == "paragraf z\nłamaniem linii"
    assert page.blocks[3].text == "- item\n- item 2"


def test_normalize_heading_texts_no_change_returns_zero():
    page = ExtractedPage(page_num=1, sections=[])
    page.blocks = [_make_block(0, 1, "section-header", "Czysty nagłówek")]
    assert normalize_heading_texts(page) == 0


def test_reclassify_matches_after_newline_in_header():
    """Prawdziwy przypadek: Vision zwrócił section-header z \\n w środku.
    Po normalize_heading_texts reclassify nie powinien błędnie degradować."""
    page = ExtractedPage(page_num=15, sections=["1. Wyniki finansowe"])
    page.blocks = [_make_block(0, 15, "section-header", "1. Wyniki\nfinansowe")]

    normalize_heading_texts(page)
    changed = reclassify_spurious_section_headers(page)

    assert changed == 0
    assert page.blocks[0].element_type == "section-header"
    assert page.blocks[0].text == "1. Wyniki finansowe"


def test_reclassify_defensive_against_newline_without_prior_normalize():
    """Nawet bez normalize_heading_texts, reclassify używa
    normalize_heading_whitespace przy porównaniu — nie degraduje."""
    page = ExtractedPage(page_num=15, sections=["1. Wyniki finansowe"])
    page.blocks = [_make_block(0, 15, "section-header", "1. Wyniki\nfinansowe")]
    changed = reclassify_spurious_section_headers(page)
    assert changed == 0
    assert page.blocks[0].element_type == "section-header"


def test_promote_matches_after_newline_in_subsection_header():
    page = ExtractedPage(page_num=15, sections=["1. Wyniki finansowe"])
    page.blocks = [_make_block(0, 15, "subsection-header", "1. Wyniki\nfinansowe")]

    normalize_heading_texts(page)
    changed = promote_matching_subsection_headers(page)

    assert changed == 1
    assert page.blocks[0].element_type == "section-header"
    assert page.blocks[0].heading_level == 1
