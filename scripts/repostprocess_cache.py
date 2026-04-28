"""Jednorazowe przepisanie cache Vision: aplikuje normalize_heading_texts +
reclassify_spurious_section_headers + promote_matching_subsection_headers
do plików data/extraction/{I..X}.json.

Gwarancja:
- zmienia `element_type` i `heading_level` bloków reklasyfikowanych/promowanych,
- zmienia `text` TYLKO dla bloków z heading_level ∈ {1, 2} (zwinięcie `\\n`
  i wielokrotnych spacji do pojedynczej spacji),
- `block_id`, `page`, `bbox`, kolejność bloków, metadane rozdziału/stron,
  a także `text` bloków nie-nagłówkowych — nietknięte.

Assert inwariantu przed zapisem; przy niezgodności przerywa bez zapisu.

Użycie:
    uv run python scripts/repostprocess_cache.py          # dry-run
    uv run python scripts/repostprocess_cache.py --apply  # zapis na dysk
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.config import VISION_CACHE_DIR
from backend.app.document.models import ExtractedChapter, ExtractedPage
from backend.app.document.vision_response import (
    normalize_heading_texts,
    promote_matching_subsection_headers,
    reclassify_spurious_section_headers,
)

CHAPTER_IDS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


def _identity_snapshot(page: ExtractedPage) -> list[tuple]:
    """Invariant: block_id/page/bbox zawsze; text tylko dla bloków
    nie-nagłówkowych (dla nagłówków normalize_heading_texts może zmienić text)."""
    return [
        (
            b.block_id,
            b.page,
            (b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1),
            None if b.heading_level in (1, 2) else b.text,
        )
        for b in page.blocks
    ]


def _process_chapter(chapter_id: str, apply: bool) -> int:
    path = VISION_CACHE_DIR / f"{chapter_id}.json"
    if not path.exists():
        print(f"[{chapter_id}] brak pliku {path} — pomijam")
        return 0

    ch = ExtractedChapter.load_json(path)
    total_changed = 0

    for page in ch.pages:
        before_snapshot = _identity_snapshot(page)
        before_types = [b.element_type for b in page.blocks]
        before_texts = [b.text for b in page.blocks]

        normalized = normalize_heading_texts(page)
        demoted = reclassify_spurious_section_headers(page)
        promoted = promote_matching_subsection_headers(page)
        changed = normalized + demoted + promoted

        after_snapshot = _identity_snapshot(page)
        if after_snapshot != before_snapshot:
            raise RuntimeError(
                f"[{chapter_id} p{page.page_num}] INWARIANT ZŁAMANY — "
                f"postprocess zmienił tożsamość bloków. Przerywam bez zapisu."
            )

        if changed:
            total_changed += changed
            after_types = [b.element_type for b in page.blocks]
            for i, (old_t, new_t) in enumerate(zip(before_types, after_types)):
                if old_t != new_t:
                    b = page.blocks[i]
                    print(
                        f"  {chapter_id} p{page.page_num} blok {b.block_id}: "
                        f"{old_t} -> {new_t} | text={b.text!r}"
                    )
            for i, old_text in enumerate(before_texts):
                b = page.blocks[i]
                if old_text != b.text:
                    print(
                        f"  {chapter_id} p{page.page_num} blok {b.block_id}: "
                        f"normalize heading | {old_text!r} -> {b.text!r}"
                    )

    if total_changed and apply:
        ch.save_json(path)
        print(f"[{chapter_id}] zapisano ({total_changed} zmian)")
    elif total_changed:
        print(f"[{chapter_id}] dry-run: {total_changed} zmian (nie zapisano)")
    else:
        print(f"[{chapter_id}] brak zmian")

    return total_changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Faktycznie zapisz zmiany na dysk (domyślnie dry-run).",
    )
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Tryb: {mode} ===")
    print(f"Cache: {VISION_CACHE_DIR}\n")

    total = 0
    for cid in CHAPTER_IDS:
        total += _process_chapter(cid, apply=args.apply)

    print(f"\nRazem reklasyfikowanych bloków: {total}")
    if not args.apply and total:
        print("Aby zapisać: uv run python scripts/repostprocess_cache.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
