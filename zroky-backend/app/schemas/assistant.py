from __future__ import annotations

from pydantic import BaseModel, Field


class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(..., min_length=1, max_length=64)


class ToolSource(BaseModel):
    tool: str
    summary: str


class AssistantChatResponse(BaseModel):
    reply: str
    sources: list[ToolSource]
    session_id: str
    off_topic: bool = False
