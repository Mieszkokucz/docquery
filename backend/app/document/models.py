from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class BBox:
    """Współrzędne prostokąta bloku na stronie PDF (x0, y0, x1, y1)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class ExtractedBlock:
    """Pojedynczy blok wydobyty z PDF."""

    block_id: str
    page: int
    element_type: str
    text: str
    bbox: BBox
    heading_level: int | None = None


@dataclass
class ExtractedPage:
    """Metadane strony + jej bloki treści."""

    page_num: int
    content_rect: BBox | None = None  # obszar treści (bez panelu nawigacyjnego)
    chapter: str | None = None  # propagowany z TOC
    sections: list[str] = field(default_factory=list)  # h1
    blocks: list[ExtractedBlock] = field(default_factory=list)


@dataclass
class ExtractedChapter:
    """Rozdział dokumentu — agreguje strony."""

    chapter_id: str  # np. "III"
    title: str
    page_start: int
    page_end: int
    pages: list[ExtractedPage] = field(default_factory=list)

    def get_all_blocks(self) -> list[ExtractedBlock]:
        return [b for p in self.pages for b in p.blocks]

    def get_blocks_by_type(self, element_type: str) -> list[ExtractedBlock]:
        return [b for b in self.get_all_blocks() if b.element_type == element_type]

    @classmethod
    def from_dict(cls, data: dict) -> ExtractedChapter:
        pages = []
        for p_data in data.get("pages", []):
            blocks = [
                ExtractedBlock(**{**b, "bbox": BBox(**b["bbox"])})
                for b in p_data.get("blocks", [])
            ]
            content_rect = (
                BBox(**p_data["content_rect"]) if p_data.get("content_rect") else None
            )
            pages.append(
                ExtractedPage(
                    page_num=p_data["page_num"],
                    content_rect=content_rect,
                    chapter=p_data.get("chapter"),
                    sections=p_data.get("sections", []),
                    blocks=blocks,
                )
            )
        return cls(
            chapter_id=data["chapter_id"],
            title=data["title"],
            page_start=data["page_start"],
            page_end=data["page_end"],
            pages=pages,
        )

    def save_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        tmp.replace(path)

    @classmethod
    def load_json(cls, path: str | Path) -> ExtractedChapter:
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


@dataclass
class DocumentMetadata:
    """Metadane całego dokumentu źródłowego."""

    source_file: str
    total_pages: int
    extraction_date: str


@dataclass
class ExtractedDocument:
    """Wynik ekstrakcji PDF."""

    metadata: DocumentMetadata
    title: str
    chapters: list[ExtractedChapter] = field(default_factory=list)

    def get_all_pages(self) -> list[ExtractedPage]:
        return [p for ch in self.chapters for p in ch.pages]

    def get_all_blocks(self) -> list[ExtractedBlock]:
        return [b for p in self.get_all_pages() for b in p.blocks]

    def get_blocks_by_type(self, element_type: str) -> list[ExtractedBlock]:
        return [b for b in self.get_all_blocks() if b.element_type == element_type]

    def get_page(self, page_num: int) -> ExtractedPage | None:
        return next((p for p in self.get_all_pages() if p.page_num == page_num), None)

    def get_chapter(self, chapter_id: str) -> ExtractedChapter | None:
        return next((ch for ch in self.chapters if ch.chapter_id == chapter_id), None)

    def get_chapter_pages(self, chapter_id: str) -> list[ExtractedPage]:
        ch = self.get_chapter(chapter_id)
        return ch.pages if ch else []

    # -- Serializacja --

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ExtractedDocument:
        metadata = DocumentMetadata(**data["metadata"])
        chapters = []
        for ch_data in data.get("chapters", []):
            pages = []
            for p_data in ch_data.get("pages", []):
                blocks = [
                    ExtractedBlock(**{**b, "bbox": BBox(**b["bbox"])})
                    for b in p_data.get("blocks", [])
                ]
                content_rect = (
                    BBox(**p_data["content_rect"])
                    if p_data.get("content_rect")
                    else None
                )
                pages.append(
                    ExtractedPage(
                        page_num=p_data["page_num"],
                        content_rect=content_rect,
                        chapter=p_data.get("chapter"),
                        sections=p_data.get("sections", []),
                        blocks=blocks,
                    )
                )
            chapters.append(
                ExtractedChapter(
                    chapter_id=ch_data["chapter_id"],
                    title=ch_data["title"],
                    page_start=ch_data["page_start"],
                    page_end=ch_data["page_end"],
                    pages=pages,
                )
            )
        return cls(metadata=metadata, title=data["title"], chapters=chapters)

    def save_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load_json(cls, path: str | Path) -> ExtractedDocument:
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
