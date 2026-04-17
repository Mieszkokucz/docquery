"""Renderowanie strony PDF → base64 z fallbackiem rozmiaru obrazu."""

from __future__ import annotations

import base64
import logging

import pymupdf

from backend.app.document.models import ExtractedPage

logger = logging.getLogger(__name__)

# Anthropic API mierzy limit na danych base64-encoded (~33% większe niż raw bytes).
# Sprawdzamy raw bytes z uwzględnieniem tego narzutu: 5 MB * (3/4) = 3.75 MB
_MAX_IMAGE_BYTES = int(5 * 1024 * 1024 * 3 / 4)

_IMAGE_ATTEMPTS = [
    (2.0, "png", None),
    (2.0, "jpeg", 85),
    (1.5, "jpeg", 85),
    (1.0, "jpeg", 85),
]


def page_to_base64(
    doc: pymupdf.Document, extracted_page: ExtractedPage
) -> tuple[str, str]:
    """Renderuje stronę PDF do obrazu i zwraca (base64, media_type).

    Jeśli PNG 2x przekracza limit 5 MB Claude API, automatycznie przechodzi
    do kolejnych wariantów (JPEG 2x → 1.5x → 1x) aż do zmieszczenia się w limicie.
    """
    page = doc[extracted_page.page_num - 1]
    for zoom, fmt, quality in _IMAGE_ATTEMPTS:
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        kwargs: dict = {"output": fmt}
        if quality is not None:
            kwargs["jpg_quality"] = quality
        img_bytes = pix.tobytes(**kwargs)
        if len(img_bytes) <= _MAX_IMAGE_BYTES:
            if fmt != "png":
                logger.warning(
                    "Strona %d: PNG za duży, użyto %s zoom=%.1f (%d kB)",
                    extracted_page.page_num,
                    fmt.upper(),
                    zoom,
                    len(img_bytes) // 1024,
                )
            media_type = "image/jpeg" if fmt == "jpeg" else "image/png"
            return base64.standard_b64encode(img_bytes).decode("utf-8"), media_type
    raise ValueError(
        f"Nie udało się zmniejszyć strony {extracted_page.page_num} poniżej 5 MB"
    )


def apply_cropboxes(doc: pymupdf.Document, pages: list[ExtractedPage]) -> None:
    """Ustawia CropBox na content_rect — wycina panel nawigacyjny."""
    for page in pages:
        if page.content_rect is None:
            continue
        cr = page.content_rect
        fitz_page = doc[page.page_num - 1]
        fitz_page.set_cropbox(pymupdf.Rect(cr.x0, cr.y0, cr.x1, cr.y1))
