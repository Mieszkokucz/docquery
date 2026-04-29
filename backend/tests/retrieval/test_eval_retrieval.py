"""Eval retrievalu na bgk_2024_qa_eval.json — regression guard dla page_hit@5.

Uruchomienie: `uv run pytest -m integration backend/tests/retrieval/test_eval_retrieval.py`.
Wymaga OPENAI_API_KEY (embeddingi text-embedding-3-small) oraz wygenerowanego
cache vision w `data/extraction_v2/`.

Baseline (notebook experiment_chunk_size_topk_v2_openai): page_hit@5 = 14/14 = 1.00.
Próg w teście: 0.85 (margines względem baseline).
"""

from __future__ import annotations

import json
import os

import pytest

from backend.app.config import DATA_DIR, V2_TOP_K, VISION_CACHE_DIR
from backend.app.retrieval import vector_store_v2 as vs
from backend.app.retrieval.bootstrap import load_and_index_v2_corpus

PAGE_HIT_AT_5_THRESHOLD = 0.85
EVAL_PATH = DATA_DIR / "eval" / "bgk_2024_qa_eval.json"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY wymagany dla testu integracyjnego",
    ),
    pytest.mark.skipif(
        not any(VISION_CACHE_DIR.glob("*.json")),
        reason=f"Brak cache vision w {VISION_CACHE_DIR} — uruchom ekstrakcję",
    ),
    pytest.mark.skipif(
        not EVAL_PATH.exists(),
        reason=f"Brak datasetu eval: {EVAL_PATH}",
    ),
]


@pytest.fixture(scope="module")
def indexed_corpus():
    vs.reset_collection()
    load_and_index_v2_corpus()
    yield
    vs.reset_collection()


@pytest.fixture(scope="module")
def eval_dataset() -> list[dict]:
    with EVAL_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def test_page_hit_at_5_meets_baseline(indexed_corpus, eval_dataset):
    misses: list[dict] = []
    hits = 0

    for item in eval_dataset:
        gt_pages = {int(p) for p in item["pages"]}
        results = vs.search_v2(item["question"], top_k=V2_TOP_K)
        retrieved_pages: set[int] = set()
        for r in results:
            retrieved_pages.update(r["pages"])

        if gt_pages & retrieved_pages:
            hits += 1
        else:
            misses.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "gt_pages": sorted(gt_pages),
                    "retrieved_pages": sorted(retrieved_pages),
                }
            )

    total = len(eval_dataset)
    page_hit_at_5 = hits / total
    print(f"\npage_hit@{V2_TOP_K} = {hits}/{total} = {page_hit_at_5:.2f}")

    if page_hit_at_5 < PAGE_HIT_AT_5_THRESHOLD:
        msg_lines = [
            f"page_hit@{V2_TOP_K} = {page_hit_at_5:.2f} < {PAGE_HIT_AT_5_THRESHOLD}",
            f"Misses ({len(misses)}):",
        ]
        for m in misses:
            msg_lines.append(
                f"  #{m['id']} gt={m['gt_pages']} retrieved={m['retrieved_pages']} "
                f"q={m['question']!r}"
            )
        pytest.fail("\n".join(msg_lines))
