from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import re
import shutil
import time

from .chunking import split_text
from .config import Settings, get_settings
from .embeddings import HashingEmbeddingModel
from .llm import ExtractiveLlmProvider, HttpJsonLlmProvider, LlmProvider, OpenAICompatibleLlmProvider
from .models import Citation, DocumentChunk, DocumentSummary, QueryPreparation, QueryResponse, RetrievalResult, SearchResult
from .pdf_loader import load_document_text
from .search import HttpJsonSearchProvider, NullSearchProvider, SearchProvider
from .store import DEFAULT_CATEGORY, JsonVectorStore


FRESHNESS_RE = re.compile(r"最新|最近|今天|昨日|昨天|本周|今年|近[一二三四五六七八九十0-9]+天|202[0-9]")


class KnowledgeAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        store: JsonVectorStore | None = None,
        search_provider: SearchProvider | None = None,
        llm_provider: LlmProvider | None = None,
    ) -> None:
        """Initialize storage, embedding, search, and answer-generation providers."""
        self.settings = settings or get_settings()
        self.embedding_model = HashingEmbeddingModel()
        self.store = store or JsonVectorStore(self.settings.index_path, self.embedding_model)
        if search_provider is not None:
            self.search_provider = search_provider
        elif self.settings.search_endpoint:
            self.search_provider = HttpJsonSearchProvider(
                self.settings.search_endpoint,
                api_key=self.settings.search_api_key,
                timeout_seconds=self.settings.search_timeout_seconds,
            )
        else:
            self.search_provider = NullSearchProvider()
        if llm_provider is not None:
            self.llm_provider = llm_provider
        elif self.settings.llm_provider == "openai" and self.settings.llm_api_key:
            self.llm_provider = OpenAICompatibleLlmProvider(
                base_url=self.settings.llm_base_url,
                model=self.settings.llm_model,
                api_key=self.settings.llm_api_key,
                temperature=self.settings.llm_temperature,
                timeout_seconds=self.settings.llm_timeout_seconds,
            )
        elif self.settings.llm_provider == "http" and self.settings.llm_endpoint:
            self.llm_provider = HttpJsonLlmProvider(
                self.settings.llm_endpoint,
                api_key=self.settings.llm_api_key,
                timeout_seconds=self.settings.llm_timeout_seconds,
            )
        else:
            self.llm_provider = ExtractiveLlmProvider()

    def upload_path(self, source_path: Path, display_name: str | None = None, category: str = "默认") -> dict[str, object]:
        """Copy a local document into the upload directory and index its chunks."""
        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)
        doc_id = self._document_id(source_path)
        saved_path = self.settings.upload_dir / f"{doc_id}{source_path.suffix.lower()}"
        if source_path.resolve() != saved_path.resolve():
            shutil.copyfile(source_path, saved_path)
        text, meta = load_document_text(saved_path)
        source_name = self._safe_display_name(display_name) or source_path.name
        meta["category"] = self._safe_category(category)
        chunks = self._make_chunks(doc_id=doc_id, source=source_name, text=text, meta=meta)
        added = self.store.add_chunks(chunks)
        return {"documentId": doc_id, "source": source_name, "category": meta["category"], "chunks": added, "meta": meta}

    def upload_bytes(self, filename: str, content: bytes, category: str = "默认") -> dict[str, object]:
        """Persist uploaded file bytes and pass the saved file into the indexing pipeline."""
        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix or ".txt"
        doc_id = hashlib.sha256(content).hexdigest()[:16]
        saved_path = self.settings.upload_dir / f"{doc_id}{suffix.lower()}"
        saved_path.write_bytes(content)
        return self.upload_path(saved_path, display_name=filename, category=category)

    def query(
        self,
        query: str,
        use_online_fallback: bool = True,
        user_id: str | None = None,
        category: str | None = None,
    ) -> QueryResponse:
        """Answer a user query with local retrieval first and optional online fallback."""
        started = time.perf_counter()
        prepared = self._prepare_query(query, use_online_fallback=use_online_fallback, user_id=user_id, category=category)
        text = self._compose_answer(
            query,
            prepared.local_results,
            prepared.search_results,
            prepared.search_error,
            prepared.freshness_required,
        )
        return self._build_query_response(prepared, text, started)

    def stream_query(
        self,
        query: str,
        use_online_fallback: bool = True,
        user_id: str | None = None,
        category: str | None = None,
    ) -> Iterator[dict[str, object]]:
        """Stream one answer as metadata, incremental text deltas, then final timing data."""
        started = time.perf_counter()
        prepared = self._prepare_query(query, use_online_fallback=use_online_fallback, user_id=user_id, category=category)
        yield {
            "event": "meta",
            "data": {
                "citations": [asdict(item) for item in self._build_citations(prepared)],
                "usedSearch": bool(prepared.used_search),
                "confidence": prepared.confidence,
                "localResults": [asdict(item) for item in prepared.local_results],
            },
        }

        for chunk in self._stream_answer(
            query,
            prepared.local_results,
            prepared.search_results,
            prepared.search_error,
            prepared.freshness_required,
        ):
            if not chunk:
                continue
            yield {"event": "delta", "data": {"text": chunk}}

        latency_ms = int((time.perf_counter() - started) * 1000)
        yield {"event": "done", "data": {"latencyMs": latency_ms}}

    def _prepare_query(
        self,
        query: str,
        use_online_fallback: bool = True,
        user_id: str | None = None,
        category: str | None = None,
    ) -> QueryPreparation:
        """Collect local hits and optional web hits before answer generation starts."""
        category_filter = self._safe_category(category) if category else None
        local_results = self.store.search(query, top_k=self.settings.top_k, category=category_filter)
        confidence = self._confidence(local_results)
        freshness_required = bool(FRESHNESS_RE.search(query))
        should_search = use_online_fallback and (freshness_required or confidence < self.settings.confidence_threshold or len(local_results) < 2)
        search_results: list[SearchResult] = []
        search_error: str | None = None

        if should_search:
            try:
                search_results = self.search_provider.search(query, limit=5)
            except Exception as exc:  # pragma: no cover - depends on external providers
                search_error = str(exc)

        return QueryPreparation(
            local_results=local_results,
            search_results=search_results,
            search_error=search_error,
            freshness_required=freshness_required,
            used_search=bool(should_search),
            confidence=self._merged_confidence(confidence, search_results, should_search),
        )

    def _build_query_response(self, prepared: QueryPreparation, text: str, started: float) -> QueryResponse:
        """Assemble the final query response payload from prepared evidence and answer text."""
        citations = self._build_citations(prepared)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return QueryResponse(
            text=text,
            citations=citations,
            used_search=prepared.used_search,
            confidence=prepared.confidence,
            latency_ms=latency_ms,
            local_results=prepared.local_results,
        )

    def _build_citations(self, prepared: QueryPreparation) -> list[Citation]:
        """Build the public citation list, including synthetic search fallback notes when needed."""
        citations = self._citations(prepared.local_results, prepared.search_results)
        if not citations and prepared.used_search and not prepared.search_results:
            citations.append(Citation(source="search", title="联网搜索未配置或无结果", fetched_at=_now()))
        return citations

    def list_documents(self) -> list[DocumentSummary]:
        """Return document-level summaries for the current local knowledge base."""
        return self.store.list_documents()

    def list_categories(self) -> list[str]:
        """Return all knowledge-base categories, keeping the default category visible."""
        categories = self.store.list_categories()
        return categories or [DEFAULT_CATEGORY]

    def add_category(self, category: str | None) -> dict[str, object]:
        """Create a knowledge-base category after normalizing and validating its name."""
        normalized = self._safe_category(category)
        if self.store.category_exists(normalized):
            raise ValueError("Category already exists")
        created = self.store.add_category(normalized)
        return {"name": normalized, "created": created}

    def rename_category(self, old_category: str | None, new_category: str | None) -> dict[str, object]:
        """Rename a category and move all existing document chunks to the new name."""
        old_normalized = self._safe_category(old_category)
        new_normalized = self._safe_category(new_category)
        if old_normalized == DEFAULT_CATEGORY:
            raise ValueError("Default category cannot be renamed")
        if not self.store.category_exists(old_normalized):
            raise LookupError("Category not found")
        if new_normalized != old_normalized and self.store.category_exists(new_normalized):
            raise ValueError("Category already exists")
        updated = self.store.rename_category(old_normalized, new_normalized)
        return {"name": new_normalized, "oldName": old_normalized, "updatedDocuments": updated}

    def delete_category(self, category: str | None) -> dict[str, object]:
        """Delete a category while preserving its documents by moving them to the default category."""
        normalized = self._safe_category(category)
        if normalized == DEFAULT_CATEGORY:
            raise ValueError("Default category cannot be deleted")
        if not self.store.category_exists(normalized):
            raise LookupError("Category not found")
        updated = self.store.delete_category(normalized, fallback_category=DEFAULT_CATEGORY)
        return {"name": normalized, "fallbackCategory": DEFAULT_CATEGORY, "updatedDocuments": updated}

    def delete_document(self, doc_id: str) -> dict[str, object]:
        """Delete one document from the vector index and remove its uploaded file when present."""
        deleted_chunks = self.store.delete_document(doc_id)
        deleted_file = False
        for path in self.settings.upload_dir.glob(f"{doc_id}.*"):
            if path.is_file():
                path.unlink()
                deleted_file = True
        return {"documentId": doc_id, "deletedChunks": deleted_chunks, "deletedFile": deleted_file}

    def update_document(self, doc_id: str, source: str | None, category: str | None) -> dict[str, object]:
        """Update one indexed document's display name and category without re-uploading it."""
        safe_source = self._safe_display_name(source)
        if not safe_source:
            raise ValueError("Document name is required")
        normalized_category = self._safe_category(category)
        updated_chunks = self.store.update_document(doc_id, safe_source, normalized_category)
        if updated_chunks == 0:
            raise LookupError("Document not found")
        return {
            "documentId": doc_id,
            "source": safe_source,
            "category": normalized_category,
            "updatedChunks": updated_chunks,
        }

    def _make_chunks(self, doc_id: str, source: str, text: str, meta: dict[str, object]) -> list[DocumentChunk]:
        """Split parsed document text into vector-store chunks with stable identifiers."""
        pieces = split_text(text, chunk_size=self.settings.chunk_size, overlap=self.settings.chunk_overlap)
        chunks: list[DocumentChunk] = []
        for index, piece in enumerate(pieces):
            chunk_id = f"{doc_id}:{index:04d}"
            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    doc_id=doc_id,
                    source=source,
                    content=piece,
                    meta={**meta, "chunkIndex": index},
                    vector_id=chunk_id,
                )
            )
        return chunks

    def _confidence(self, results: list[RetrievalResult]) -> float:
        """Estimate answer confidence from retrieval score strength and result coverage."""
        if not results:
            return 0.0
        top_score = results[0].score
        avg_score = sum(item.score for item in results) / len(results)
        score_norm = min(1.0, top_score / 0.55)
        coverage = min(1.0, len([item for item in results if item.score >= 0.18]) / 3)
        grounding = min(1.0, avg_score / 0.35)
        return min(1.0, 0.35 * score_norm + 0.4 * coverage + 0.25 * grounding)

    def _merged_confidence(self, local_confidence: float, search_results: list[SearchResult], searched: bool) -> float:
        """Adjust final confidence after optional online search evidence is considered."""
        if search_results:
            return min(1.0, max(local_confidence, 0.78))
        if searched:
            return min(local_confidence, 0.55)
        return local_confidence

    def _compose_answer(
        self,
        query: str,
        local_results: list[RetrievalResult],
        search_results: list[SearchResult],
        search_error: str | None,
        freshness_required: bool,
    ) -> str:
        """Generate the final Markdown answer and append fallback notes when needed."""
        answer, search_error = self._generate_answer_text(query, local_results, search_results, search_error)
        notes = self._supplemental_answer_lines(search_error, freshness_required, search_results)
        lines = [self._shorten_answer(answer)]
        if notes:
            lines.append("")
            lines.extend(notes)
        return "\n".join(line for line in lines if line)

    def _stream_answer(
        self,
        query: str,
        local_results: list[RetrievalResult],
        search_results: list[SearchResult],
        search_error: str | None,
        freshness_required: bool,
    ) -> Iterator[str]:
        """Yield answer fragments first, then append any fallback or freshness notes."""
        streamed = False
        try:
            for chunk in self.llm_provider.stream_answer(query, local_results[:3], search_results[:3]):
                if not chunk:
                    continue
                streamed = True
                yield chunk
        except Exception as exc:  # pragma: no cover - depends on external providers
            search_error = search_error or f"LLM 调用失败，已使用本地摘要降级：{exc}"
            fallback_answer = self._shorten_answer(ExtractiveLlmProvider().answer(query, local_results[:3], search_results[:3]))
            if fallback_answer:
                streamed = True
                yield fallback_answer

        if not streamed:
            fallback_answer = self._shorten_answer(ExtractiveLlmProvider().answer(query, local_results[:3], search_results[:3]))
            if fallback_answer:
                yield fallback_answer

        notes = self._supplemental_answer_lines(search_error, freshness_required, search_results)
        if notes:
            yield "\n\n" + "\n".join(notes)

    def _generate_answer_text(
        self,
        query: str,
        local_results: list[RetrievalResult],
        search_results: list[SearchResult],
        search_error: str | None,
    ) -> tuple[str, str | None]:
        """Generate one complete Markdown answer and downgrade to extractive mode on provider failure."""
        try:
            answer = self.llm_provider.answer(query, local_results[:3], search_results[:3])
        except Exception as exc:  # pragma: no cover - depends on external providers
            answer = ExtractiveLlmProvider().answer(query, local_results[:3], search_results[:3])
            search_error = search_error or f"LLM 调用失败，已使用本地摘要降级：{exc}"
        return answer, search_error

    def _supplemental_answer_lines(
        self,
        search_error: str | None,
        freshness_required: bool,
        search_results: list[SearchResult],
    ) -> list[str]:
        """Return supplemental explanation lines appended after the main answer body."""
        lines: list[str] = []
        if freshness_required and not search_results:
            lines.append("这个问题包含时效性要求，但当前没有可用的联网搜索结果。")
        if search_error:
            lines.append(f"补充说明：{search_error}")
        return lines

    def _citations(self, local_results: list[RetrievalResult], search_results: list[SearchResult]) -> list[Citation]:
        """Convert local and web evidence into response citations."""
        citations: list[Citation] = []
        for result in local_results[:3]:
            citations.append(Citation(source="local", title=result.source, chunk_id=result.chunk_id))
        for result in search_results[:3]:
            citations.append(
                Citation(
                    source="web",
                    title=result.title,
                    url=result.url,
                    fetched_at=result.fetched_at,
                )
            )
        return citations

    def _shorten(self, text: str, limit: int = 220) -> str:
        """Compact a single text fragment to a maximum display length."""
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return compact[: limit - 1].rstrip() + "…"

    def _shorten_answer(self, text: str, limit: int = 1400) -> str:
        """Compact generated Markdown while preserving line breaks between sections."""
        compact_lines = [self._shorten(line, 260) for line in text.splitlines()]
        compact = "\n".join(line for line in compact_lines if line.strip())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 1].rstrip() + "…"

    def _document_id(self, source_path: Path) -> str:
        """Build a stable short document id from file contents."""
        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        return digest[:16]

    def _safe_display_name(self, filename: str | None) -> str | None:
        """Return a basename-only file label safe for display and citations."""
        if not filename:
            return None
        name = Path(filename).name.strip()
        return name or None

    def _safe_category(self, category: str | None) -> str:
        """Normalize a user-provided knowledge-base category name."""
        if not category:
            return DEFAULT_CATEGORY
        compact = re.sub(r"\s+", " ", category).strip()
        return compact[:40] if compact else DEFAULT_CATEGORY


def query_response_to_dict(response: QueryResponse) -> dict[str, object]:
    """Convert internal dataclass response fields to the public API naming style."""
    payload = asdict(response)
    payload["usedSearch"] = payload.pop("used_search")
    payload["latencyMs"] = payload.pop("latency_ms")
    payload["localResults"] = payload.pop("local_results")
    return payload


def document_summary_to_dict(summary: DocumentSummary) -> dict[str, object]:
    """Convert document summary dataclass fields to the public API naming style."""
    payload = asdict(summary)
    payload["documentId"] = payload.pop("doc_id")
    return payload


def _now() -> str:
    """Return the current UTC timestamp for synthetic citations."""
    return datetime.now(timezone.utc).isoformat()
