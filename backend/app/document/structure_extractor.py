"""Pipeline ekstrakcji struktury PDF → ExtractedDocument (bez bloków)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pymupdf

from backend.app.document.models import (
    BBox,
    DocumentMetadata,
    ExtractedChapter,
    ExtractedDocument,
    ExtractedPage,
)

# ---------------------------------------------------------------------------
# Regex patterns (z TOC raportu BGK)
# ---------------------------------------------------------------------------
PATTERN_CHAPTER_NUM = re.compile(r"^[IVXLCDM]+\s*$")
PATTERN_CHAPTER_FULL = re.compile(r"^([IVXLCDM]+)\s+(.+?)\s*$")
PATTERN_PAGE_ONLY = re.compile(r"^\d+\s*$")
# PATTERN_SUB_FULL = re.compile(r"^\d+\.\s+(.+?)\s*\.{2,}\s*(\d+)\s*$")
# PATTERN_SUB_START = re.compile(r"^\d+\.\s+(.+)$")
PATTERN_SUB_FULL = re.compile(r"^(\d+\.\s+.+?)\s*\.{2,}\s*(\d+)\s*$")
PATTERN_SUB_START = re.compile(r"^(\d+\.\s+.+)$")
RE_DOTS_END = re.compile(r"^(.*?)\s*\.{2,}\s*(\d+)\s*$")
RE_ROMAN = re.compile(r"^([IVXLCDM]+)\s")


# ---------------------------------------------------------------------------
# Wewnętrzne helpery
# ---------------------------------------------------------------------------


def _extract_title(doc: pymupdf.Document) -> str:
    """Wydobywa tytuł dokumentu ze strony 1 (font TideSans-600Bunny, size=33, kolor biały)."""
    first_page = doc[0]
    data = first_page.get_text("dict")
    title_parts: list[str] = []
    for block in data["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                hex_color = f"#{span['color']:06X}"
                if (
                    span["font"] == "TideSans-600Bunny"
                    and round(span["size"]) == 33
                    and hex_color == "#FFFFFF"
                ):
                    text = span["text"].strip()
                    if text:
                        title_parts.append(text)
    return " ".join(title_parts)


def _parse_toc(doc: pymupdf.Document) -> list[tuple[str, int, int]]:
    """Parsuje spis treści ze strony 2. Zwraca [(title, page_1based, level), ...]."""
    toc_entries: list[tuple[str, int, int]] = []
    toc_page = doc[1]
    data = toc_page.get_text("dict")

    for block in data["blocks"]:
        if block["type"] != 0:
            continue
        lines = [
            "".join(s["text"] for s in line["spans"]).strip() for line in block["lines"]
        ]
        lines = [l for l in lines if l]
        i = 0
        while i < len(lines):
            line = lines[i]

            # 3-liniowy nagłówek: "I" / "Jedyny taki bank" / "3"
            if (
                PATTERN_CHAPTER_NUM.match(line)
                and i + 2 < len(lines)
                and PATTERN_PAGE_ONLY.match(lines[i + 2])
            ):
                toc_entries.append(
                    (
                        f"{line.strip()} {lines[i + 1].strip()}",
                        int(lines[i + 2].strip()),
                        1,
                    )
                )
                i += 3
                continue

            # 2-liniowy nagłówek: "VIII Perspektywy" / "142"
            mc = PATTERN_CHAPTER_FULL.match(line)
            if mc and i + 1 < len(lines) and PATTERN_PAGE_ONLY.match(lines[i + 1]):
                toc_entries.append(
                    (
                        f"{mc.group(1)} {mc.group(2).strip()}",
                        int(lines[i + 1].strip()),
                        1,
                    )
                )
                i += 2
                continue

            # Podpunkt pełny: "1. Tytuł ..... 42"
            ms = PATTERN_SUB_FULL.match(line)
            if ms:
                toc_entries.append((ms.group(1).strip(), int(ms.group(2)), 2))
                i += 1
                continue

            # Podpunkt zawijany: dwie linie
            ms2 = PATTERN_SUB_START.match(line)
            if ms2 and i + 1 < len(lines):
                m2 = RE_DOTS_END.match(lines[i + 1])
                if m2:
                    title_full = f"{ms2.group(1).strip()} {m2.group(1).strip()}".strip()
                    toc_entries.append((title_full, int(m2.group(2)), 2))
                    i += 2
                    continue
            i += 1

    return toc_entries


def _compute_ranges(
    toc_entries: list[tuple[str, int, int]], total_pages: int
) -> list[tuple[str, int, int, int]]:
    """Wylicza zakresy stron. Zwraca [(title, start, end, level), ...]."""
    toc_with_ranges = []
    for i, (title, page, level) in enumerate(toc_entries):
        start_page = page
        end_page = total_pages
        for j in range(i + 1, len(toc_entries)):
            _, next_page, next_level = toc_entries[j]
            if next_level <= level:
                end_page = max(start_page, next_page - 1)
                break
        toc_with_ranges.append((title, start_page, end_page, level))
    return toc_with_ranges


def _chapter_id(title: str, idx: int) -> str:
    """Wyciąga cyfrę rzymską z tytułu, np. 'III Pracownicy' → 'III'."""
    m = RE_ROMAN.match(title)
    return m.group(1) if m else f"{idx + 1:02d}"


def _sections_for_page(
    page_num: int, subsections: list[tuple[str, int, int]]
) -> list[str]:
    """Zwraca listę tytułów sekcji (level=2) zaczynających się na danej stronie wg ToC."""
    return [title for title, page, level in subsections if page == page_num]


def _populate_content_rects(
    doc: pymupdf.Document,
    document: ExtractedDocument,
    nav_threshold: float = 210,
) -> None:
    """Wyznacza content_rect per strona (pełna strona minus lewy panel nawigacyjny)."""
    for page in document.get_all_pages():
        fitz_page = doc[page.page_num - 1]
        r = fitz_page.rect
        page.content_rect = BBox(
            x0=nav_threshold,
            y0=r.y0,
            x1=r.x1,
            y1=r.y1,
        )


# ---------------------------------------------------------------------------
# Publiczne API
# ---------------------------------------------------------------------------


def extract_structure(
    pdf_path: str | Path,
) -> tuple[ExtractedDocument, pymupdf.Document]:
    """Pełny pipeline: PDF → ExtractedDocument (bez bloków) + otwarty pymupdf.Document."""
    pdf_path = Path(pdf_path)
    doc = pymupdf.open(pdf_path)

    title = _extract_title(doc)
    toc_entries = _parse_toc(doc)
    toc_with_ranges = _compute_ranges(toc_entries, len(doc))

    metadata = DocumentMetadata(
        source_file=str(pdf_path.resolve()),
        total_pages=len(doc),
        extraction_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    document = ExtractedDocument(metadata=metadata, title=title)

    # Budowanie rozdziałów i stron
    chapters_raw = [(t, s, e) for t, s, e, lvl in toc_with_ranges if lvl == 1]
    sections_from_toc = [(t, p, lvl) for t, p, lvl in toc_entries if lvl == 2]

    for idx, (ch_title, ch_start, ch_end) in enumerate(chapters_raw):
        chapter_sections = [
            (t, p, lvl) for t, p, lvl in sections_from_toc if ch_start <= p <= ch_end
        ]
        pages = []
        for page_num in range(ch_start, ch_end + 1):
            sections = _sections_for_page(page_num, chapter_sections)
            pages.append(
                ExtractedPage(
                    page_num=page_num,
                    chapter=ch_title,
                    sections=sections,
                )
            )
        document.chapters.append(
            ExtractedChapter(
                chapter_id=_chapter_id(ch_title, idx),
                title=ch_title,
                page_start=ch_start,
                page_end=ch_end,
                pages=pages,
            )
        )

    _populate_content_rects(doc, document)

    return document, doc
