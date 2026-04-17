from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.routes import router
from backend.app.config import CHUNK_OVERLAP, CHUNK_SIZE, PDF_PATH
from backend.app.document.naive_processor import chunk_pages, extract_pages
from backend.app.retrieval.vector_store import index_chunks


@asynccontextmanager
async def lifespan(app: FastAPI):
    pages = extract_pages(str(PDF_PATH))
    chunks = chunk_pages(pages, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    index_chunks(chunks)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)
