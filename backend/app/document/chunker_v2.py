"""Chunkowanie ExtractedDocument (v2) → lista chunków gotowych do embeddingu.

Każdy chunk ma dwa pola tekstowe: `search_text` (wzbogacony o prefiks
`chapter > section` i ew. `Strony: ...`, używany do embeddingu) oraz `content`
(surowy tekst bloków, bez prefiksu — do cytowania/wyświetlania).

Reguły:
- `section-header` zamyka poprzedni chunk i aktualizuje kontekst sekcji
  używany w prefiksie kolejnych chunków. Sam tekst nagłówka nie trafia do
  treści chunka — pojawia się wyłącznie w prefiksie `chapter > section`.
- `table` i `infographic` zawsze są osobnym chunkiem; jeśli tuż nad nimi (w
  reading order, po pominięciu bloków SKIP) stoi `caption`, jego tekst jest
  prefiksem treści chunka. Media NIE przerywają bieżącego chunka tekstowego —
  tekst przed i po medium łączy się w jeden ciągły chunk tekstowy (bez markera
  w miejscu medium). Chunk tekstowy tną wyłącznie `section-header` oraz limit
  `max_chars`.
- `picture` (logo, znaki wodne, dekoracyjne grafiki) jest pomijany.
- Pozostałe typy (text, list, subsection-header, footnote, identifier,
  osierocony caption, …) są akumulowane w bieżącym chunku tekstowym w
  kolejności czytania.
- `max_chars` ogranicza rozmiar chunka tekstowego — podział zawsze na granicy
  bloku, nigdy w środku bloku.
- `overlap_chars` (domyślnie 0) — gdy sekcja dzieli się z powodu `max_chars`,
  następny chunk zaczyna się od ogona poprzedniego. Ogon brany jest w trybie
  znakowym: ostatnie `overlap_chars` znaków tekstu chunka, ze startem
  dobieranym wg kolejnych preferencji: (1) granica zdania — `.?!` + whitespace
  + wielka litera (w tym polskie diakrytyki); (2) fallback — granica wyrazu
  (po pierwszej spacji w oknie); (3) ostateczny fallback, gdy w oknie nie ma
  spacji — cały window. Overlap nigdy nie przekracza `overlap_chars`. Trafia
  do następnego chunka jako syntetyczny blok o `block_id = "overlap-<idx>"`.
  Overlap działa tylko w obrębie jednej sekcji — `section-header` twardo
  przerywa ciągłość (media nie przerywają buffora).

Known limitation: caption na końcu strony N + tabela na początku strony N+1 nie
zostaną sparowane (wykrywanie caption jest per-strona).
"""

from __future__ import annotations

import re

from backend.app.document.models import (
    BBox,
    ExtractedBlock,
    ExtractedDocument,
    ExtractedPage,
)

_SENTENCE_END = re.compile(r"[.!?]\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])")
_WORD_BOUNDARY = re.compile(r"\s+")

SKIP: set[str] = {"picture"}
MEDIA: set[str] = {"table", "infographic"}


def _format_pages(pages: list[int]) -> str:
    if len(pages) == 1:
        return str(pages[0])
    contiguous = all(b - a == 1 for a, b in zip(pages, pages[1:]))
    if contiguous:
        return f"{pages[0]}–{pages[-1]}"
    return ", ".join(str(p) for p in pages)


def _build_prefix(chapter: str | None, section: str | None, pages: list[int]) -> str:
    if chapter and section:
        header = f"{chapter} > {section}"
    elif chapter:
        header = chapter
    elif section:
        header = section
    else:
        header = ""
    lines: list[str] = []
    if header:
        lines.append(header)
    if len(pages) > 1:
        lines.append(f"Strony: {_format_pages(pages)}")
    return "\n".join(lines)


def _compose_text(prefix: str, content: str) -> str:
    return f"{prefix}\n\n{content}" if prefix else content


def _preceding_caption(blocks: list[ExtractedBlock], idx: int) -> ExtractedBlock | None:
    """Zwraca caption stojący bezpośrednio nad blocks[idx] (pomijając SKIP)."""
    j = idx - 1
    while j >= 0:
        t = blocks[j].element_type
        if t in SKIP:
            j -= 1
            continue
        return blocks[j] if t == "caption" else None
    return None


def _next_non_skip_is_media(blocks: list[ExtractedBlock], idx: int) -> bool:
    j = idx + 1
    while j < len(blocks):
        t = blocks[j].element_type
        if t in SKIP:
            j += 1
            continue
        return t in MEDIA
    return False


def _tail_text_for_overlap(text: str, limit: int) -> str:
    """Ostatnie `limit` znaków `text`, przesunięte do sensownej granicy.

    Dwupoziomowy wybór startu w oknie ostatnich `limit` znaków:
    1. Granica zdania: `.?!` + whitespace + wielka litera (łapie polskie
       diakrytyki). Overlap zaczyna się od tej wielkiej litery.
    2. Fallback: granica wyrazu — start po pierwszej spacji w oknie.
    3. Ostateczny fallback (brak spacji w oknie, np. jeden wyraz > limit):
       cały window.
    """
    if limit <= 0 or not text:
        return ""
    window = text if len(text) <= limit else text[-limit:]
    match = _SENTENCE_END.search(window)
    if match is not None:
        return window[match.end() :]
    space = _WORD_BOUNDARY.search(window)
    if space is not None:
        return window[space.end() :]
    return window


def chunk_document(
    document: ExtractedDocument,
    max_chars: int = 1500,
    overlap_chars: int = 0,
) -> list[dict]:
    """Zamienia ExtractedDocument na listę chunków (dict) gotowych do indeksowania."""
    if overlap_chars < 0:
        raise ValueError("overlap_chars musi być >= 0")
    if overlap_chars and overlap_chars >= max_chars:
        raise ValueError("overlap_chars musi być mniejsze od max_chars")

    chunks: list[dict] = []
    idx = 0
    current_section: str | None = None

    buf_blocks: list[ExtractedBlock] = []
    buf_pages: list[int] = []
    buf_chapter: str | None = None
    buf_section: str | None = None

    def flush(carry: bool = False) -> None:
        nonlocal idx, buf_blocks, buf_pages, buf_chapter, buf_section
        if not buf_blocks:
            return
        content = "\n\n".join(b.text for b in buf_blocks)
        prefix = _build_prefix(buf_chapter, buf_section, buf_pages)
        chunks.append(
            {
                "search_text": _compose_text(prefix, content),
                "content": content,
                "page": buf_pages[0],
                "pages": list(buf_pages),
                "chapter": buf_chapter,
                "section": buf_section,
                "element_type": "text",
                "chunk_index": idx,
                "source_blocks": [b.block_id for b in buf_blocks],
            }
        )
        idx += 1

        tail: list[ExtractedBlock] = []
        if carry and overlap_chars > 0:
            tail_text = _tail_text_for_overlap(content, overlap_chars)
            if tail_text:
                last_page = buf_pages[-1]
                tail = [
                    ExtractedBlock(
                        block_id=f"overlap-{idx}",
                        page=last_page,
                        element_type="text",
                        text=tail_text,
                        bbox=BBox(0.0, 0.0, 0.0, 0.0),
                    )
                ]

        if tail:
            buf_blocks = list(tail)
            buf_pages = sorted({b.page for b in tail})
            # buf_chapter/buf_section zachowujemy — ogon należy do tej samej sekcji
        else:
            buf_blocks = []
            buf_pages = []
            buf_chapter = None
            buf_section = None

    def add_page(page_num: int) -> None:
        if not buf_pages or buf_pages[-1] != page_num:
            buf_pages.append(page_num)

    def open_buffer_with(block: ExtractedBlock, page: ExtractedPage) -> None:
        nonlocal buf_chapter, buf_section
        buf_blocks.append(block)
        add_page(page.page_num)
        buf_chapter = page.chapter
        buf_section = current_section

    for page in document.get_all_pages():
        blocks = page.blocks
        for i, block in enumerate(blocks):
            t = block.element_type

            if t in SKIP:
                continue

            if t in MEDIA:
                caption = _preceding_caption(blocks, i)
                content = f"{caption.text}\n\n{block.text}" if caption else block.text
                prefix = _build_prefix(page.chapter, current_section, [page.page_num])
                source_blocks = (
                    [caption.block_id, block.block_id] if caption else [block.block_id]
                )
                chunks.append(
                    {
                        "search_text": _compose_text(prefix, content),
                        "content": content,
                        "page": page.page_num,
                        "pages": [page.page_num],
                        "chapter": page.chapter,
                        "section": current_section,
                        "element_type": t,
                        "chunk_index": idx,
                        "source_blocks": source_blocks,
                    }
                )
                idx += 1
                continue

            if t == "section-header":
                flush()
                current_section = block.text
                continue

            if t == "caption" and _next_non_skip_is_media(blocks, i):
                continue

            prospective = (
                sum(len(b.text) for b in buf_blocks)
                + 2 * len(buf_blocks)
                + len(block.text)
            )
            if buf_blocks and prospective > max_chars:
                flush(carry=True)

            if not buf_blocks:
                open_buffer_with(block, page)
            else:
                buf_blocks.append(block)
                add_page(page.page_num)

    flush()
    return chunks
