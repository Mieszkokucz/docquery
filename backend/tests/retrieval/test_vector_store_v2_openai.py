"""Integracja vector_store_v2 z prawdziwym OpenAI text-embedding-3-small.

Uruchomienie: `uv run pytest -m integration`. Domyślnie pomijane przez
`addopts = -m 'not integration'`. Wymaga OPENAI_API_KEY w środowisku.
"""

from __future__ import annotations

import os

import pytest

from backend.app.retrieval import vector_store_v2 as vs

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY wymagany dla testu integracyjnego",
    ),
]


@pytest.fixture(autouse=True)
def _fresh_collection():
    vs.reset_collection()
    yield
    vs.reset_collection()


def test_search_returns_top_k_matching_chunk_openai():
    chunks = [
        {
            "search_text": "BGK > Przychody: przychody z tytułu odsetek w 2024 roku",
            "content": "Przychody z tytułu odsetek w 2024 roku wyniosły 5 mld zł.",
            "page": 10,
            "pages": [10],
            "chapter": "BGK",
            "section": "Przychody",
            "element_type": "text",
            "chunk_index": 0,
        },
        {
            "search_text": "BGK > Zatrudnienie: pracownicy banku",
            "content": "Na koniec 2024 roku bank zatrudniał 2100 osób.",
            "page": 11,
            "pages": [11],
            "chapter": "BGK",
            "section": "Zatrudnienie",
            "element_type": "text",
            "chunk_index": 1,
        },
        {
            "search_text": "BGK > Nagrody: wyróżnienia branżowe",
            "content": "Bank otrzymał nagrodę za najlepszy raport zintegrowany.",
            "page": 12,
            "pages": [12],
            "chapter": "BGK",
            "section": "Nagrody",
            "element_type": "text",
            "chunk_index": 2,
        },
    ]
    vs.index_v2_chunks(chunks)

    results = vs.search_v2("ile bank zarobił z odsetek", top_k=2)

    assert len(results) == 2
    assert "odsetek" in results[0]["content"].lower()
