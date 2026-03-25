import re

from fastapi import APIRouter

from backend.app.api.models import ChatRequest, ChatResponse, Source
from backend.app.conversation.history import add_message, get_history
from backend.app.conversation.llm_client import ask
from backend.app.conversation.prompt_builder import build_prompt
from backend.app.retrieval.vector_store import search

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    history = get_history(request.session_id)
    chunks = search(request.question)
    system, messages = build_prompt(request.question, chunks, history)
    answer = ask(messages, system)

    add_message(request.session_id, "user", request.question)
    add_message(request.session_id, "assistant", answer)

    cited_pages = set(map(int, re.findall(r"\[Strona (\d+)\]", answer)))
    sources = [
        Source(page=c["page"], text=c["text"])
        for c in chunks
        if c["page"] in cited_pages
    ]
    return ChatResponse(answer=answer, sources=sources)
