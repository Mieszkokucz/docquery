"""Unit testy dla prompt_builder_v2.py — bez kluczy API."""

from __future__ import annotations

import pytest

from backend.app.conversation.prompt_builder_v2 import (
    SYSTEM_PROMPT,
    build_prompt_v2,
    format_context,
    match_sources,
    parse_citations,
)


def _chunk(
    page: int,
    pages: list[int],
    element_type: str = "text",
    content: str = "Treść.",
    chapter: str | None = "I",
    section: str | None = "Wstęp",
    chunk_index: int = 0,
) -> dict:
    return {
        "page": page,
        "pages": pages,
        "element_type": element_type,
        "content": content,
        "chapter": chapter,
        "section": section,
        "chunk_index": chunk_index,
    }


# ---------------------------------------------------------------------------
# format_context
# ---------------------------------------------------------------------------


def test_format_context_single_page():
    c = _chunk(page=5, pages=[5], content="Tekst na stronie piątej.")
    result = format_context([c])
    assert "[Strona 5]" in result
    assert "(text)" in result
    assert "I › Wstęp" in result
    assert '"Tekst na stronie piątej."' in result


def test_format_context_multi_page():
    c = _chunk(page=10, pages=[10, 11, 12], content="Długi tekst.")
    result = format_context([c])
    assert "[Strony 10–12]" in result


def test_format_context_no_chapter_or_section():
    c = _chunk(page=1, pages=[1], chapter=None, section=None, content="Bez nagłówka.")
    result = format_context([c])
    assert "›" not in result
    assert '"Bez nagłówka."' in result


def test_format_context_multiple_chunks_separated():
    c1 = _chunk(page=1, pages=[1], content="Pierwszy.", chunk_index=0)
    c2 = _chunk(page=2, pages=[2], content="Drugi.", chunk_index=1)
    result = format_context([c1, c2])
    parts = result.split("\n\n")
    assert len(parts) == 2


# ---------------------------------------------------------------------------
# parse_citations
# ---------------------------------------------------------------------------


def test_parse_citations_single_page():
    result = parse_citations("Wynik to 42. [Strona 42]")
    assert result == [("text", {42})]


def test_parse_citations_page_range():
    result = parse_citations("Dane finansowe [Strony 12-15] są kluczowe.")
    assert result == [("text", {12, 13, 14, 15})]


def test_parse_citations_page_range_em_dash():
    result = parse_citations("Dane [Strony 12–15].")
    assert result == [("text", {12, 13, 14, 15})]


def test_parse_citations_table():
    result = parse_citations("Wyniki pokazuje [Tabela, s. 7].")
    assert result == [("table", {7})]


def test_parse_citations_infographic():
    result = parse_citations("Schemat na [Infografika, s. 33].")
    assert result == [("infographic", {33})]


def test_parse_citations_multiple():
    text = "Patrz [Strona 5] i [Tabela, s. 7] oraz [Infografika, s. 33]."
    result = parse_citations(text)
    assert ("text", {5}) in result
    assert ("table", {7}) in result
    assert ("infographic", {33}) in result
    assert len(result) == 3


def test_parse_citations_empty():
    assert parse_citations("Brak żadnych cytatów.") == []


# ---------------------------------------------------------------------------
# match_sources
# ---------------------------------------------------------------------------


def test_match_sources_basic_match():
    chunks = [_chunk(page=5, pages=[5], element_type="text", chunk_index=0)]
    citations = [("text", {5})]
    result = match_sources(chunks, citations)
    assert len(result) == 1
    assert result[0]["chunk_index"] == 0


def test_match_sources_no_match_wrong_type():
    chunks = [_chunk(page=5, pages=[5], element_type="table", chunk_index=0)]
    citations = [("text", {5})]
    assert match_sources(chunks, citations) == []


def test_match_sources_no_match_wrong_page():
    chunks = [_chunk(page=5, pages=[5], element_type="text", chunk_index=0)]
    citations = [("text", {99})]
    assert match_sources(chunks, citations) == []


def test_match_sources_deduplication():
    chunks = [
        _chunk(page=5, pages=[5], element_type="text", chunk_index=7),
        _chunk(page=5, pages=[5], element_type="text", chunk_index=7),  # duplikat
    ]
    citations = [("text", {5})]
    result = match_sources(chunks, citations)
    assert len(result) == 1


def test_match_sources_empty_inputs():
    assert match_sources([], [("text", {1})]) == []
    assert match_sources([_chunk(page=1, pages=[1])], []) == []


def test_match_sources_multi_page_chunk():
    chunks = [_chunk(page=10, pages=[10, 11, 12], element_type="text", chunk_index=3)]
    citations = [("text", {11})]
    result = match_sources(chunks, citations)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# build_prompt_v2
# ---------------------------------------------------------------------------


def test_build_prompt_v2_returns_system_and_messages():
    chunks = [_chunk(page=1, pages=[1])]
    system, messages = build_prompt_v2("Pytanie?", chunks)
    assert system == SYSTEM_PROMPT
    assert isinstance(messages, list)


def test_build_prompt_v2_first_turn_no_history():
    chunks = [_chunk(page=1, pages=[1], content="Kontekst.")]
    _, messages = build_prompt_v2("Co to jest?", chunks)
    assert messages[0]["role"] == "user"
    assert "Kontekst." in messages[0]["content"]
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Co to jest?"


def test_build_prompt_v2_first_turn_empty_history():
    chunks = [_chunk(page=1, pages=[1])]
    _, messages = build_prompt_v2("Pierwsze pytanie.", chunks, history=[])
    assert messages[-1]["content"] == "Pierwsze pytanie."


def test_build_prompt_v2_multiturn_history_preserved():
    chunks = [_chunk(page=1, pages=[1])]
    history = [
        {"role": "user", "content": "Poprzednie pytanie."},
        {"role": "assistant", "content": "Poprzednia odpowiedź."},
    ]
    _, messages = build_prompt_v2("Nowe pytanie.", chunks, history=history)
    roles = [m["role"] for m in messages]
    contents = [m["content"] for m in messages]
    assert "Poprzednie pytanie." in contents
    assert "Poprzednia odpowiedź." in contents
    assert messages[-1]["content"] == "Nowe pytanie."
    assert messages[-1]["role"] == "user"
