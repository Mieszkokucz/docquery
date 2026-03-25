import uuid

from pydantic import BaseModel, Field


class Source(BaseModel):
    page: int
    text: str


class ChatRequest(BaseModel):
    question: str
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
