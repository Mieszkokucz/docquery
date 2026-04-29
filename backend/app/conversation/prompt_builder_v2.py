"""Prompt builder dla ścieżki RAG v2 (chunki z chunker_v2 + vector_store_v2).

Vision-chunki mają bogatsze metadane niż naive (`chapter`, `section`, `pages`,
`element_type`, `content`) — kontekst dla modelu formatujemy z tym nagłówkiem
i pozwalamy na cytaty w postaci [Strona X], [Strony X-Y], [Tabela, s. X],
[Infografika, s. X]. Po odpowiedzi parsujemy cytaty i dobieramy źródłowe
chunki (`match_sources`).
"""

from __future__ import annotations

import re

SYSTEM_PROMPT = (
    "Jesteś asystentem odpowiadającym na pytania wyłącznie na podstawie dostarczonych "
    "fragmentów dokumentu.\n\n"
    "Zasady:\n"
    "1. Odpowiadaj WYŁĄCZNIE na podstawie dostarczonych fragmentów. "
    "Nie korzystaj z wiedzy zewnętrznej.\n"
    "2. Każdą tezę potwierdź dosłownym cytatem z dokumentu w cudzysłowie.\n"
    "3. Przy każdym cytacie podaj numer strony lub zakres stron:\n"
    "   - Jeśli cytat pochodzi z jednej strony: [Strona X]\n"
    "   - Jeśli cytat obejmuje kilka kolejnych stron: [Strony X-Y]\n"
    "4. Fragmenty oznaczone jako TABELA lub INFOGRAFIKA traktuj jako dane pomocnicze.\n"
    "   NIE cytuj ich dosłownie. Zamiast tego opisz zawarte w nich informacje własnymi "
    "słowami i oznacz odwołanie w formacie:\n"
    "   - [Tabela, s. X] lub [Infografika, s. X]\n"
    "5. Jeśli informacji nie ma w dostarczonym kontekście — powiedz o tym wprost. "
    "Nie zgaduj i nie konfabuluj.\n"
    "6. Jeśli pytanie odwołuje się do wcześniejszej rozmowy "
    "(np. 'to', 'a rok wcześniej', 'ten dokument'), wykorzystaj "
    "historię konwersacji do rozwiązania referencji.\n"
    "7. Odpowiadaj w tym samym języku, w którym zadano pytanie."
)


_CITATION_RE = re.compile(
    r"\[(?:"
    r"Strona\s+(?P<page>\d+)"
    r"|Strony\s+(?P<p_start>\d+)\s*[-–]\s*(?P<p_end>\d+)"
    r"|Tabela,\s*s\.\s*(?P<t_page>\d+)"
    r"|Infografika,\s*s\.\s*(?P<i_page>\d+)"
    r")\]"
)


def format_context(chunks: list[dict]) -> str:
    parts = []
    for c in chunks:
        header_bits = [x for x in (c["chapter"], c["section"]) if x]
        header = " › ".join(header_bits)
        pages_str = (
            f"Strona {c['pages'][0]}"
            if len(c["pages"]) == 1
            else f"Strony {c['pages'][0]}–{c['pages'][-1]}"
        )
        parts.append(
            f"[{pages_str}] ({c['element_type']}) {header}\n\"{c['content']}\""
        )
    return "\n\n".join(parts)


def build_prompt_v2(
    question: str,
    chunks: list[dict],
    history: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    """Zwraca (system, messages) dla Anthropic API."""
    context = format_context(chunks)
    messages: list[dict] = [
        {"role": "user", "content": f"Document context:\n\n{context}"},
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})
    return SYSTEM_PROMPT, messages


def parse_citations(answer: str) -> list[tuple[str, set[int]]]:
    """Zwraca listę (element_type, {pages}) z cytatów w odpowiedzi."""
    out: list[tuple[str, set[int]]] = []
    for m in _CITATION_RE.finditer(answer):
        if m.group("page"):
            out.append(("text", {int(m.group("page"))}))
        elif m.group("p_start"):
            s, e = int(m.group("p_start")), int(m.group("p_end"))
            out.append(("text", set(range(s, e + 1))))
        elif m.group("t_page"):
            out.append(("table", {int(m.group("t_page"))}))
        elif m.group("i_page"):
            out.append(("infographic", {int(m.group("i_page"))}))
    return out


def match_sources(
    retrieved: list[dict],
    citations: list[tuple[str, set[int]]],
) -> list[dict]:
    """Unikatowe (po chunk_index) chunki pasujące do cytatów."""
    seen: set[int] = set()
    sources: list[dict] = []
    for c in retrieved:
        for etype, pages in citations:
            if c["element_type"] != etype:
                continue
            if any(p in pages for p in c["pages"]):
                key = c["chunk_index"]
                if key not in seen:
                    seen.add(key)
                    sources.append(c)
                break
    return sources
