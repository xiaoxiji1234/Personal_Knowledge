from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Iterable

from .embeddings import HashingEmbeddingModel
from .models import DocumentChunk, DocumentSummary, RetrievalResult


DEFAULT_CATEGORY = "默认"


class JsonVectorStore:
    def __init__(self, path: Path, embedding_model: HashingEmbeddingModel) -> None:
        """Load an on-disk JSON vector store and attach the embedding model."""
        self.path = path
        self.embedding_model = embedding_model
        self.chunks: dict[str, DocumentChunk] = {}
        self.categories: set[str] = {DEFAULT_CATEGORY}
        self.load()

    def load(self) -> None:
        """Read chunk and category data from disk if an index file already exists."""
        if not self.path.exists():
            self.chunks = {}
            self.categories = {DEFAULT_CATEGORY}
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.chunks = {
            item["id"]: DocumentChunk(
                id=item["id"],
                doc_id=item["doc_id"],
                source=item["source"],
                content=item["content"],
                meta=item.get("meta", {}),
                vector_id=item.get("vector_id"),
                embedding=item.get("embedding", {}),
            )
            for item in payload.get("chunks", [])
        }
        loaded_categories = {_safe_category_name(item) for item in payload.get("categories", [])}
        chunk_categories = {_safe_category_name(chunk.meta.get("category")) for chunk in self.chunks.values()}
        self.categories = {DEFAULT_CATEGORY, *loaded_categories, *chunk_categories}

    def save(self) -> None:
        """Persist all chunks, embeddings, and categories to the JSON index file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "chunks": [asdict(chunk) for chunk in self.chunks.values()],
            "categories": self.list_categories(),
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_chunks(self, chunks: Iterable[DocumentChunk]) -> int:
        """Embed and upsert chunks into the vector store."""
        count = 0
        for chunk in chunks:
            chunk.embedding = self.embedding_model.embed(chunk.content)
            chunk.vector_id = chunk.vector_id or chunk.id
            category = _safe_category_name(chunk.meta.get("category"))
            chunk.meta["category"] = category
            self.categories.add(category)
            self.chunks[chunk.id] = chunk
            count += 1
        self.save()
        return count

    def search(self, query: str, top_k: int = 5, category: str | None = None) -> list[RetrievalResult]:
        """Return the highest-scoring local chunks for a query."""
        query_embedding = self.embedding_model.embed(query)
        scored: list[RetrievalResult] = []
        for chunk in self.chunks.values():
            if category and _safe_category_name(chunk.meta.get("category")) != category:
                continue
            score = self.embedding_model.similarity(query_embedding, chunk.embedding)
            if score <= 0:
                continue
            scored.append(
                RetrievalResult(
                    chunk_id=chunk.id,
                    score=score,
                    content=chunk.content,
                    source=chunk.source,
                    meta=chunk.meta,
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    def count(self) -> int:
        """Return the total number of stored chunks."""
        return len(self.chunks)

    def list_documents(self) -> list[DocumentSummary]:
        """Group chunks by document id and return document-level summaries."""
        grouped: dict[str, list[DocumentChunk]] = {}
        for chunk in self.chunks.values():
            grouped.setdefault(chunk.doc_id, []).append(chunk)

        documents: list[DocumentSummary] = []
        for doc_id, chunks in grouped.items():
            first = sorted(chunks, key=lambda item: item.id)[0]
            documents.append(
                DocumentSummary(
                    doc_id=doc_id,
                    source=first.source,
                    chunks=len(chunks),
                    parser=_optional_str(first.meta.get("parser")),
                    quality=_optional_str(first.meta.get("quality")),
                    pages=_optional_int(first.meta.get("pages")),
                    category=_optional_str(first.meta.get("category")) or DEFAULT_CATEGORY,
                )
            )
        documents.sort(key=lambda item: (item.category, item.source))
        return documents

    def delete_document(self, doc_id: str) -> int:
        """Remove every chunk belonging to one document id and persist the index."""
        chunk_ids = [chunk_id for chunk_id, chunk in self.chunks.items() if chunk.doc_id == doc_id]
        for chunk_id in chunk_ids:
            del self.chunks[chunk_id]
        if chunk_ids:
            self.save()
        return len(chunk_ids)

    def update_document(self, doc_id: str, source: str, category: str) -> int:
        """Update one document's display name and category across all of its chunks."""
        updated = 0
        normalized_category = _safe_category_name(category)
        self.categories.add(normalized_category)
        for chunk in self.chunks.values():
            if chunk.doc_id != doc_id:
                continue
            chunk.source = source
            chunk.meta["category"] = normalized_category
            updated += 1
        if updated:
            self.save()
        return updated

    def list_categories(self) -> list[str]:
        """Return all persisted categories with the default category first."""
        categories = {DEFAULT_CATEGORY, *self.categories}
        return [DEFAULT_CATEGORY, *sorted(category for category in categories if category != DEFAULT_CATEGORY)]

    def add_category(self, category: str) -> bool:
        """Add one category to the store and report whether it was newly created."""
        normalized = _safe_category_name(category)
        if normalized in self.categories:
            return False
        self.categories.add(normalized)
        self.save()
        return True

    def rename_category(self, old_category: str, new_category: str) -> int:
        """Rename a category and update all chunks that currently belong to it."""
        old_normalized = _safe_category_name(old_category)
        new_normalized = _safe_category_name(new_category)
        self.categories.discard(old_normalized)
        self.categories.add(new_normalized)
        updated = 0
        for chunk in self.chunks.values():
            if _safe_category_name(chunk.meta.get("category")) == old_normalized:
                chunk.meta["category"] = new_normalized
                updated += 1
        self.save()
        return updated

    def delete_category(self, category: str, fallback_category: str = DEFAULT_CATEGORY) -> int:
        """Delete one category and reassign its chunks to the fallback category."""
        normalized = _safe_category_name(category)
        fallback = _safe_category_name(fallback_category)
        self.categories.discard(normalized)
        self.categories.add(fallback)
        updated = 0
        for chunk in self.chunks.values():
            if _safe_category_name(chunk.meta.get("category")) == normalized:
                chunk.meta["category"] = fallback
                updated += 1
        self.save()
        return updated

    def category_exists(self, category: str) -> bool:
        """Return whether a normalized category is currently persisted."""
        return _safe_category_name(category) in self.categories


def _optional_str(value: object) -> str | None:
    """Convert metadata values to optional strings for public document summaries."""
    if value is None:
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    """Convert metadata values to optional integers when possible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_category_name(value: object) -> str:
    """Convert stored category metadata into a non-empty category name."""
    if value is None:
        return DEFAULT_CATEGORY
    category = str(value).strip()
    return category or DEFAULT_CATEGORY
