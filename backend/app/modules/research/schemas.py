"""Request/response shapes for the Research endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class ResearchSource(BaseModel):
    title: str
    url: str


class ResearchResponse(BaseModel):
    answer: str
    sources: list[ResearchSource]
