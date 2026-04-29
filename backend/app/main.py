import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.routes import router
from backend.app.retrieval.bootstrap import load_and_index_v2_corpus


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "Brak OPENAI_API_KEY — indeksowanie v2 wymaga kluczy OpenAI "
            "(embeddingi text-embedding-3-small)."
        )

    load_and_index_v2_corpus()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)
