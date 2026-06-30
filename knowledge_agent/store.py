from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Iterable

from .embeddings import HashingEmbeddingModel
from .models import DocumentChunk, DocumentSummary, RetrievalResult


DEFAULT_CATEGORY = "默认"
MAX_FOLDER_DEPTH = 3


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
        loaded_categories = {_safe_folder_path(item) for item in payload.get("categories", [])}
        chunk_categories = {_safe_folder_path(chunk.meta.get("folderPath") or chunk.meta.get("category")) for chunk in self.chunks.values()}
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
            category = _safe_folder_path(chunk.meta.get("folderPath") or chunk.meta.get("category"))
            chunk.meta["category"] = category
            chunk.meta["folderPath"] = category
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
            if category and _safe_folder_path(chunk.meta.get("folderPath") or chunk.meta.get("category")) != category:
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
            folder_path = _optional_str(first.meta.get("folderPath") or first.meta.get("category")) or DEFAULT_CATEGORY
            documents.append(
                DocumentSummary(
                    doc_id=doc_id,
                    source=first.source,
                    chunks=len(chunks),
                    parser=_optional_str(first.meta.get("parser")),
                    quality=_optional_str(first.meta.get("quality")),
                    pages=_optional_int(first.meta.get("pages")),
                    category=folder_path,
                    folder_path=folder_path,
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
        normalized_category = _safe_folder_path(category)
        self.categories.add(normalized_category)
        for chunk in self.chunks.values():
            if chunk.doc_id != doc_id:
                continue
            chunk.source = source
            chunk.meta["category"] = normalized_category
            chunk.meta["folderPath"] = normalized_category
            updated += 1
        if updated:
            self.save()
        return updated

    def list_categories(self) -> list[str]:
        """Return all persisted categories with the default category first."""
        categories = {DEFAULT_CATEGORY, *self.categories}
        return [DEFAULT_CATEGORY, *sorted(category for category in categories if category != DEFAULT_CATEGORY)]

    def list_folders(self) -> list[str]:
        """Return all persisted folder paths with the default folder first."""
        return self.list_categories()

    def add_category(self, category: str) -> bool:
        """Add one category to the store and report whether it was newly created."""
        normalized = _safe_folder_path(category)
        if normalized in self.categories:
            return False
        self.categories.add(normalized)
        self.save()
        return True

    def add_folder(self, folder_path: str) -> bool:
        """Add one folder path to the store and report whether it was newly created."""
        return self.add_category(folder_path)

    def rename_category(self, old_category: str, new_category: str) -> int:
        """Rename a category and update all chunks that currently belong to it."""
        old_normalized = _safe_folder_path(old_category)
        new_normalized = _safe_folder_path(new_category)
        self.categories = {
            _replace_folder_prefix(category, old_normalized, new_normalized) for category in self.categories
        }
        updated = 0
        for chunk in self.chunks.values():
            current = _safe_folder_path(chunk.meta.get("folderPath") or chunk.meta.get("category"))
            if _is_same_or_child_folder(current, old_normalized):
                next_path = _replace_folder_prefix(current, old_normalized, new_normalized)
                chunk.meta["category"] = next_path
                chunk.meta["folderPath"] = next_path
                updated += 1
        self.save()
        return updated

    def rename_folder(self, old_path: str, new_path: str) -> int:
        """Rename a folder path and all nested child folder paths."""
        return self.rename_category(old_path, new_path)

    def delete_category(self, category: str, fallback_category: str = DEFAULT_CATEGORY) -> int:
        """Delete one category and reassign its chunks to the fallback category."""
        normalized = _safe_folder_path(category)
        fallback = _safe_folder_path(fallback_category)
        self.categories = {category for category in self.categories if not _is_same_or_child_folder(category, normalized)}
        self.categories.add(fallback)
        updated = 0
        for chunk in self.chunks.values():
            current = _safe_folder_path(chunk.meta.get("folderPath") or chunk.meta.get("category"))
            if _is_same_or_child_folder(current, normalized):
                chunk.meta["category"] = fallback
                chunk.meta["folderPath"] = fallback
                updated += 1
        self.save()
        return updated

    def delete_folder(self, folder_path: str, fallback_folder: str = DEFAULT_CATEGORY) -> int:
        """Delete one folder path and move nested documents into the fallback folder."""
        return self.delete_category(folder_path, fallback_category=fallback_folder)

    def category_exists(self, category: str) -> bool:
        """Return whether a normalized category is currently persisted."""
        return _safe_folder_path(category) in self.categories

    def folder_exists(self, folder_path: str) -> bool:
        """Return whether a normalized folder path is currently persisted."""
        return self.category_exists(folder_path)


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


def _safe_folder_path(value: object) -> str:
    """Convert stored folder metadata into a normalized non-empty folder path."""
    if value is None:
        return DEFAULT_CATEGORY
    parts = [part.strip() for part in str(value).split("/")]
    clean_parts = [part for part in parts if part]
    if not clean_parts:
        return DEFAULT_CATEGORY
    return "/".join(clean_parts[:MAX_FOLDER_DEPTH])


def _is_same_or_child_folder(folder_path: str, parent_path: str) -> bool:
    """Return whether one folder path is the same as or nested below another."""
    return folder_path == parent_path or folder_path.startswith(f"{parent_path}/")


def _replace_folder_prefix(folder_path: str, old_prefix: str, new_prefix: str) -> str:
    """Replace one folder path prefix while preserving child path suffixes."""
    if folder_path == old_prefix:
        return new_prefix
    if folder_path.startswith(f"{old_prefix}/"):
        return f"{new_prefix}/{folder_path[len(old_prefix) + 1:]}"
    return folder_path
