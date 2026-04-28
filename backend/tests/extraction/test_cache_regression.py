"""Snapshot regression dla cache vision (data/extraction/I-X.json).

Baseline liczbowy wyznaczony z commita d8ee585. Używa `>=` nie `==` —
drobny drift (np. podział bloku) OK; kolaps (puste strony, brak sekcji) wywali.

Jeśli cache zostanie zregenerowany z nowszym promptem / modelem i liczby
wzrosną w sposób stabilny — zaktualizować CACHE_INVARIANTS do nowego baseline.
"""

import pytest

from backend.app.config import VISION_CACHE_DIR
from backend.app.document.models import ExtractedChapter

# Baseline: (page_start, page_end, min_total_blocks, min_section_headers)
CACHE_INVARIANTS: dict[str, tuple[int, int, int, int]] = {
    "I": (3, 13, 90, 6),
    "II": (14, 28, 215, 4),
    "III": (29, 46, 225, 4),
    "IV": (47, 52, 60, 3),
    "V": (53, 103, 717, 8),
    "VI": (104, 130, 305, 7),
    "VII": (131, 141, 159, 10),
    "VIII": (142, 147, 58, 2),
    "IX": (148, 159, 47, 4),
    "X": (160, 184, 349, 9),
}


def _cache_path(chapter_id: str):
    path = VISION_CACHE_DIR / f"{chapter_id}.json"
    if not path.exists():
        pytest.skip(f"Brak cache: {path}")
    return path


@pytest.mark.parametrize("chapter_id,baseline", list(CACHE_INVARIANTS.items()))
def test_cache_invariants(chapter_id, baseline):
    page_start, page_end, min_blocks, min_headers = baseline
    ch = ExtractedChapter.load_json(_cache_path(chapter_id))

    assert ch.chapter_id == chapter_id
    assert ch.page_start == page_start, (
        f"{chapter_id} page_start={ch.page_start}, baseline={page_start}"
    )
    assert ch.page_end == page_end, (
        f"{chapter_id} page_end={ch.page_end}, baseline={page_end}"
    )

    total = len(ch.get_all_blocks())
    assert total >= min_blocks, (
        f"{chapter_id} total_blocks={total}, baseline>={min_blocks}"
    )

    headers = len(ch.get_blocks_by_type("section-header"))
    assert headers >= min_headers, (
        f"{chapter_id} section-headers={headers}, baseline>={min_headers}"
    )


@pytest.mark.parametrize("chapter_id", list(CACHE_INVARIANTS.keys()))
def test_cache_json_loads(chapter_id):
    """Sanity: każdy I-X.json deserializuje się do ExtractedChapter bez błędu."""
    ExtractedChapter.load_json(_cache_path(chapter_id))
