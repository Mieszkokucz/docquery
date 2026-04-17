import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from backend.app.config import EMBEDDING_MODEL, TOP_K

# Module-level — initialized once
_client = chromadb.Client()
_embedding_fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
_collection = _client.get_or_create_collection(
    "documents", embedding_function=_embedding_fn
)


def index_chunks(chunks: list[dict]) -> None:
    """Add chunks to vector store. Each chunk needs: text, page, chunk_index."""
    _collection.add(
        documents=[c["text"] for c in chunks],
        metadatas=[
            {"page": c["page"], "chunk_index": c["chunk_index"]} for c in chunks
        ],
        ids=[f"p{c['page']}_c{c['chunk_index']}" for c in chunks],
    )


def search(query: str, top_k: int = TOP_K) -> list[dict]:
    """Query vector store, return top_k results with text, metadata, distance."""
    results = _collection.query(query_texts=[query], n_results=top_k)
    output = []
    for i in range(len(results["documents"][0])):
        output.append(
            {
                "text": results["documents"][0][i],
                "page": results["metadatas"][0][i]["page"],
                "chunk_index": results["metadatas"][0][i]["chunk_index"],
                "distance": results["distances"][0][i],
            }
        )
    return output
