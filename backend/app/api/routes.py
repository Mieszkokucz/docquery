from fastapi import APIRouter

from backend.app.api.models import ChatRequest, ChatResponse, Source
from backend.app.conversation.history import add_message, get_history
from backend.app.conversation.llm_client import ask
from backend.app.conversation.prompt_builder_v2 import (
    build_prompt_v2,
    match_sources,
    parse_citations,
)
from backend.app.retrieval.vector_store_v2 import search_v2

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    history = get_history(request.session_id)
    chunks = search_v2(request.question)
    system, messages = build_prompt_v2(request.question, chunks, history)
    answer = ask(messages, system)

    add_message(request.session_id, "user", request.question)
    add_message(request.session_id, "assistant", answer)

    sources = [
        Source(
            pages=c["pages"],
            element_type=c["element_type"],
            chapter=c["chapter"],
            section=c["section"],
            content=c["content"],
        )
        for c in match_sources(chunks, parse_citations(answer))
    ]
    return ChatResponse(answer=answer, sources=sources)
