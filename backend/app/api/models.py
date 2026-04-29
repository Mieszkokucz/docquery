import uuid

from pydantic import BaseModel, Field


class Source(BaseModel):
    pages: list[int]
    element_type: str
    chapter: str | None = None
    section: str | None = None
    content: str


class ChatRequest(BaseModel):
    question: str
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
