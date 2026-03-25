from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from backend.app.api.routes import router
from backend.app.document.naive_processor import chunk_pages, extract_pages
from backend.app.retrieval.vector_store import index_chunks

PDF_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "raport_2024_wybrane_strony.pdf"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pages = extract_pages(str(PDF_PATH))
    chunks = chunk_pages(pages, chunk_size=999999)
    index_chunks(chunks)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)
