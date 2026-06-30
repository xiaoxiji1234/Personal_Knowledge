from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Citation:
    source: str
    title: str
    url: str | None = None
    chunk_id: str | None = None
    fetched_at: str | None = None


@dataclass
class DocumentChunk:
    id: str
    doc_id: str
    source: str
    content: str
    meta: dict[str, Any] = field(default_factory=dict)
    vector_id: str | None = None
    embedding: dict[str, float] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    chunk_id: str
    score: float
    content: str
    source: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    fetched_at: str


@dataclass
class QueryResponse:
    text: str
    citations: list[Citation]
    used_search: bool
    confidence: float
    latency_ms: int
    local_results: list[RetrievalResult] = field(default_factory=list)


@dataclass
class QueryPreparation:
    local_results: list[RetrievalResult]
    search_results: list[SearchResult]
    search_error: str | None
    freshness_required: bool
    used_search: bool
    confidence: float


@dataclass
class DocumentSummary:
    doc_id: str
    source: str
    chunks: int
    category: str = "默认"
    folder_path: str = "默认"
    parser: str | None = None
    quality: str | None = None
    pages: int | None = None
