"""Vector store dla chunków z chunker_v2.

Pola `search_text` (embedowane) vs `content` (zwracane do cytowania) trzymane
osobno, bogate metadane (chapter, section, pages, element_type).
"""

from __future__ import annotations

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from backend.app.config import V2_EMBEDDING_MODEL, V2_TOP_K

_COLLECTION_NAME = "v2_chunks"

_client = chromadb.Client()
_embedding_fn = None  # lazy: tworzony przy pierwszym użyciu lub podmieniony w testach
_collection = None    # lazy: tworzony przez _ensure_collection()


def _ensure_collection():
    global _embedding_fn, _collection
    if _embedding_fn is None:
        _embedding_fn = OpenAIEmbeddingFunction(
            api_key_env_var="OPENAI_API_KEY",
            model_name=V2_EMBEDDING_MODEL,
        )
    if _collection is None:
        _collection = _client.get_or_create_collection(
            _COLLECTION_NAME, embedding_function=_embedding_fn
        )
    return _collection


def _format_pages(pages: list[int]) -> str:
    """[12] → '12'; [12,13] → '12-13'; [12,14] → '12,14'; [12,13,14,18] → '12-14,18'."""
    if not pages:
        return ""
    pages = sorted(set(pages))
    groups: list[tuple[int, int]] = []
    start = prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        groups.append((start, prev))
        start = prev = p
    groups.append((start, prev))
    return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in groups)


def _parse_pages(s: str) -> list[int]:
    if not s:
        return []
    out: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def index_v2_chunks(chunks: list[dict]) -> None:
    """Indeksuje chunki z chunker_v2. Każdy chunk potrzebuje pól:
    search_text, content, page, pages, chapter, section, element_type, chunk_index.
    """
    if not chunks:
        return
    _ensure_collection().add(
        documents=[c["search_text"] for c in chunks],
        metadatas=[
            {
                "page": c["page"],
                "pages": _format_pages(c["pages"]),
                "chunk_index": c["chunk_index"],
                "chapter": c["chapter"] or "",
                "section": c["section"] or "",
                "element_type": c["element_type"],
                "content": c["content"],
            }
            for c in chunks
        ],
        ids=[f"vp{c['page']}_c{c['chunk_index']}" for c in chunks],
    )


def search_v2(query: str, top_k: int = V2_TOP_K) -> list[dict]:
    """Zwraca top_k chunków v2. `content` i `search_text` oddzielnie."""
    results = _ensure_collection().query(query_texts=[query], n_results=top_k)
    output: list[dict] = []
    for i in range(len(results["documents"][0])):
        meta = results["metadatas"][0][i]
        output.append(
            {
                "content": meta["content"],
                "search_text": results["documents"][0][i],
                "page": meta["page"],
                "pages": _parse_pages(meta["pages"]),
                "chapter": meta["chapter"] or None,
                "section": meta["section"] or None,
                "element_type": meta["element_type"],
                "chunk_index": meta["chunk_index"],
                "distance": results["distances"][0][i],
            }
        )
    return output


def reset_collection() -> None:
    """Usuwa i odtwarza kolekcję. Do użycia w testach i notebookach eksploracyjnych."""
    global _collection, _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = OpenAIEmbeddingFunction(
            api_key_env_var="OPENAI_API_KEY",
            model_name=V2_EMBEDDING_MODEL,
        )
    try:
        _client.delete_collection(_COLLECTION_NAME)
    except Exception:
        pass
    _collection = _client.get_or_create_collection(
        _COLLECTION_NAME, embedding_function=_embedding_fn
    )
