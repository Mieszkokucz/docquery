import pymupdf


def extract_pages(pdf_path: str) -> list[dict]:
    doc = pymupdf.open(pdf_path)
    pages = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text()
        if text.strip():
            pages.append({"text": text, "page": i})
    doc.close()
    return pages


def chunk_pages(
    pages: list[dict],
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[dict]:
    chunks = []
    step = chunk_size - overlap
    for page in pages:
        text = page["text"]
        page_num = page["page"]
        chunk_index = 0
        for start in range(0, len(text), step):
            chunk_text = text[start : start + chunk_size]
            if chunk_text.strip():
                chunks.append({
                    "text": chunk_text,
                    "page": page_num,
                    "chunk_index": chunk_index,
                })
                chunk_index += 1
    return chunks
