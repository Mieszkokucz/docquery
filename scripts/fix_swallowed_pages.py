"""Naprawa "połkniętych" bloków w cache Vision.

Na niektórych stronach json_repair (fallback w `vision_response.clean_response`)
sklejał końcówkę odpowiedzi Vision w pojedynczy stringowy blok. Skutek:
w polu `text` pewnego bloku siedzi surowy JSON kolejnych elementów.

Skrypt:
  1. Skanuje `VISION_CACHE_DIR`, znajduje bloki-połykacze (text zawiera `"element_type"`).
  2. Regexem (z twardym domknięciem `"}` + lookahead na granicę kolekcji) wyciąga
     zagnieżdżone obiekty.
  3. Podmienia text połykacza na jego prawdziwą treść (prefix), dokleja odzyskane
     bloki z kolejnymi `block_id`.
  4. Inwariant: pozostałe bloki na stronie nietknięte; renumeracja tylko nowych
     pozycji na końcu.

Użycie:
    uv run python scripts/fix_swallowed_pages.py          # dry-run
    uv run python scripts/fix_swallowed_pages.py --apply  # zapis
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.config import VISION_CACHE_DIR
from backend.app.document.models import BBox, ExtractedBlock, ExtractedChapter
from backend.app.document.vision_response import infer_heading_level

CHAPTER_IDS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]

NESTED_MARK = '"element_type"'
NESTED_OBJ_RE = re.compile(
    r'\{"element_type"\s*:\s*"(?P<et>[^"]+)"\s*,\s*"text"\s*:\s*"(?P<tx>.*?)"\}'
    r'(?=\s*(?:,\s*\{"element_type"|\]\s*\}|$))',
    re.DOTALL,
)
PREFIX_TAIL_RE = re.compile(r'"\.?"\}\s*,?\s*$')


def split_swallower(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Zwraca (prefix_właściwej_treści, [(element_type, text), ...])."""
    matches = list(NESTED_OBJ_RE.finditer(text))
    if not matches:
        return text, []
    prefix = text[: matches[0].start()]
    prefix = PREFIX_TAIL_RE.sub("", prefix.rstrip())
    prefix = prefix.rstrip('",. \n\t')
    return prefix, [(m.group("et"), m.group("tx")) for m in matches]


def _process_page(page, page_num: int) -> int:
    """Zwraca liczbę odzyskanych bloków (0 jeśli brak połknięcia)."""
    swallower_idx = next(
        (i for i, b in enumerate(page.blocks) if NESTED_MARK in (b.text or "")), None
    )
    if swallower_idx is None:
        return 0

    sw = page.blocks[swallower_idx]
    prefix, recovered = split_swallower(sw.text)
    if not recovered:
        return 0

    expected = sw.text.count(NESTED_MARK)
    if len(recovered) != expected:
        raise RuntimeError(
            f"p{page_num}: mismatch — regex złapał {len(recovered)}, "
            f'a "element_type" występuje {expected} razy. Przerywam.'
        )

    sw.text = prefix

    next_idx = len(page.blocks)
    for et, tx in recovered:
        page.blocks.append(
            ExtractedBlock(
                block_id=f"p{page_num}_b{next_idx}",
                page=page_num,
                element_type=et,
                text=tx,
                bbox=BBox(x0=0, y0=0, x1=0, y1=0),
                heading_level=infer_heading_level(et),
            )
        )
        next_idx += 1

    return len(recovered)


def _process_chapter(chapter_id: str, apply: bool) -> int:
    path = VISION_CACHE_DIR / f"{chapter_id}.json"
    if not path.exists():
        print(f"[{chapter_id}] brak pliku {path} — pomijam")
        return 0

    ch = ExtractedChapter.load_json(path)
    total = 0
    for page in ch.pages:
        n = _process_page(page, page.page_num)
        if n:
            total += n
            print(f"  {chapter_id} p{page.page_num}: odzyskano {n} bloków")

    if total and apply:
        ch.save_json(path)
        print(f"[{chapter_id}] zapisano ({total} nowych bloków)")
    elif total:
        print(f"[{chapter_id}] dry-run: {total} nowych bloków (nie zapisano)")
    else:
        print(f"[{chapter_id}] brak połknięć")

    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Zapisz zmiany na dysk.")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Tryb: {mode} ===")
    print(f"Cache: {VISION_CACHE_DIR}\n")

    total = 0
    for cid in CHAPTER_IDS:
        total += _process_chapter(cid, apply=args.apply)

    print(f"\nRazem odzyskanych bloków: {total}")
    if not args.apply and total:
        print("Aby zapisać: uv run python scripts/fix_swallowed_pages.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
