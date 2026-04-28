"""Testy jakości ekstrakcji Vision porównując cache z ręcznym ground truth.

Nie wywołuje API — operuje wyłącznie na data/extraction_v2/ (cache Sonnet).
Pomija testy jeśli brak pliku GT lub brak cache dla danego rozdziału.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import pytest

from backend.app.config import PDF_PATH, VISION_CACHE_DIR
from backend.app.document.extraction_cache import load_cached_chapters
from backend.app.document.structure_extractor import extract_structure

EVAL_DIR = Path(__file__).parents[3] / "data" / "eval"
GT_FILENAMES = [
    "bgk_extraction_p054_gt.json",
    "bgk_extraction_p059_gt.json",
    "bgk_extraction_p095_gt.json",
]
TEXTUAL_TYPES = {"text", "list", "identifier", "caption", "footnote", "subsection-header"}
TABLE_TYPE = "table"
JOINED_SIM_THRESHOLD = 0.99


# ---------------------------------------------------------------------------
# Helpers (skopiowane z notebooka test_vision_extraction_on_gt_joined)
# ---------------------------------------------------------------------------


def join_textual(elements: list[dict]) -> str:
    parts = [e["text"] for e in elements if e["element_type"] in TEXTUAL_TYPES]
    return "\n\n".join(parts)


def _split_table_text(text: str) -> tuple[str, str]:
    parts = text.split("\n\n", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", text)


def normalize_md_table(md: str) -> str:
    lines = md.strip().splitlines()
    normalized = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^\|[\s\-:|]+\|[\s\-:|]*$", stripped):
            sep_cells = stripped.split("|")
            new_cells = []
            for cell in sep_cells:
                c = cell.strip()
                if not c:
                    new_cells.append("")
                    continue
                left = ":" if c.startswith(":") else ""
                right = ":" if c.endswith(":") and c != ":" else ""
                new_cells.append(f"{left}-{right}")
            normalized.append("|".join(new_cells))
        else:
            cells = stripped.split("|")
            norm_cells = []
            for c in cells:
                # usuń inline bold (**text**) i italic (*text*)
                c = re.sub(r"\*\*(.+?)\*\*", r"\1", c)
                c = re.sub(r"\*(.+?)\*", r"\1", c)
                norm_cells.append(c.strip())
            normalized.append("|".join(norm_cells))
    return "\n".join(normalized)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ground_truths() -> dict[int, list[dict]]:
    result: dict[int, list[dict]] = {}
    for filename in GT_FILENAMES:
        path = EVAL_DIR / filename
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        result[data["page"]] = data["elements"]
    return result


@pytest.fixture(scope="module")
def cached_document():
    if not PDF_PATH.exists():
        pytest.skip(f"Brak PDF: {PDF_PATH}")
    document, doc = extract_structure(PDF_PATH)
    doc.close()
    load_cached_chapters(document, VISION_CACHE_DIR)
    return document


# ---------------------------------------------------------------------------
# Test A — joined text similarity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page_num", [54, 59, 95])
def test_joined_text_similarity(page_num, ground_truths, cached_document):
    if page_num not in ground_truths:
        pytest.skip(f"Brak GT dla strony {page_num}")

    extracted_page = cached_document.get_page(page_num)
    if extracted_page is None or not extracted_page.blocks:
        pytest.skip(f"Strona {page_num} nie ma bloków w cache")

    gt_joined = join_textual(ground_truths[page_num])
    pred_elements = [
        {"element_type": b.element_type, "text": b.text} for b in extracted_page.blocks
    ]
    pred_joined = join_textual(pred_elements)

    sim = SequenceMatcher(None, gt_joined, pred_joined).ratio()
    assert sim >= JOINED_SIM_THRESHOLD, (
        f"p{page_num}: joined_sim={sim:.3f} < {JOINED_SIM_THRESHOLD}"
    )


# ---------------------------------------------------------------------------
# Test C — tabele: liczba + markdown exact match
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page_num", [59])
def test_table_exact_match(page_num, ground_truths, cached_document):
    if page_num not in ground_truths:
        pytest.skip(f"Brak GT dla strony {page_num}")

    extracted_page = cached_document.get_page(page_num)
    if extracted_page is None or not extracted_page.blocks:
        pytest.skip(f"Strona {page_num} nie ma bloków w cache")

    gt_tables = [e for e in ground_truths[page_num] if e["element_type"] == TABLE_TYPE]
    pred_tables = [
        {"element_type": b.element_type, "text": b.text}
        for b in extracted_page.blocks
        if b.element_type == TABLE_TYPE
    ]

    assert len(pred_tables) == len(gt_tables), (
        f"p{page_num}: liczba tabel — expected {len(gt_tables)}, got {len(pred_tables)}"
    )

    for i, (gt_tbl, pred_tbl) in enumerate(zip(gt_tables, pred_tables)):
        _, gt_md = _split_table_text(gt_tbl["text"])
        _, pred_md = _split_table_text(pred_tbl["text"])
        gt_norm = normalize_md_table(gt_md).strip()
        pred_norm = normalize_md_table(pred_md).strip()
        assert gt_norm == pred_norm, (
            f"p{page_num} tabela #{i}: markdown mismatch\n"
            f"Expected:\n{gt_norm}\n\nGot:\n{pred_norm}"
        )
