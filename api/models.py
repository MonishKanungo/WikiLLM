from pydantic import BaseModel
from typing import Optional


class LLMConfig(BaseModel):
    model: str          # e.g. "openai/gpt-4o-mini", "anthropic/claude-3-haiku", "gemini/gemini-pro"
    api_key: str
    api_base: Optional[str] = None  # for custom / local endpoints


class QueryRequest(BaseModel):
    question: str
    llm: LLMConfig


class IngestMetadata(BaseModel):
    filename: str
    llm: LLMConfig


class LintRequest(BaseModel):
    llm: LLMConfig


class WikiPage(BaseModel):
    name: str
    content: str


class QueryResponse(BaseModel):
    answer: str
    cited_pages: list[str]


class IngestResponse(BaseModel):
    message: str
    pages_updated: list[str]


class WikiListResponse(BaseModel):
    pages: list[str]


class SaveAnswerRequest(BaseModel):
    page_name: str      # snake_case slug, e.g. "ai_comparison_2024"
    page_title: str     # Human readable, e.g. "AI Comparison 2024"
    content: str        # The answer/markdown content to save


class SaveAnswerResponse(BaseModel):
    message: str
    page_name: str
