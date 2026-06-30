from __future__ import annotations

import json

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from .auth import AuthStore
from .config import get_settings
from .service import KnowledgeAgent, document_summary_to_dict, query_response_to_dict


app = FastAPI(title="Personal Knowledge QA Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
agent = KnowledgeAgent()
auth_store = AuthStore(get_settings().users_path)


def sse_event(event: str, data: dict[str, object]) -> str:
    """Encode one server-sent event payload for the streaming query endpoint."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def read_bearer_token(authorization: str | None) -> str | None:
    """Extract one bearer token from the Authorization header when present."""
    value = (authorization or "").strip()
    if not value.lower().startswith("bearer "):
        return None
    token = value[7:].strip()
    return token or None


def require_auth(authorization: str | None = Header(default=None)) -> dict[str, str]:
    """Require a valid bearer token before allowing protected knowledge-base access."""
    token = read_bearer_token(authorization)
    user = auth_store.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录后再访问知识库")
    return user


class QueryRequest(BaseModel):
    """Request body for asking the knowledge agent a question."""

    query: str = Field(min_length=1)
    useOnlineFallback: bool = True
    userId: Optional[str] = None
    category: Optional[str] = None


class CategoryRequest(BaseModel):
    """Request body for creating or renaming a knowledge-base category."""

    name: str = Field(min_length=1, max_length=40)


class AuthRegisterRequest(BaseModel):
    """Request body for creating one new local account."""

    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=6, max_length=128)
    displayName: str = Field(min_length=2, max_length=40)
    rememberMe: bool = False


class AuthLoginRequest(BaseModel):
    """Request body for authenticating one existing local account."""

    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=6, max_length=128)
    rememberMe: bool = False


class DocumentUpdateRequest(BaseModel):
    """Request body for renaming one document and moving it into another category."""

    source: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=40)


@app.get("/health")
def health(current_user: dict[str, str] = Depends(require_auth)) -> dict[str, object]:
    """Return a lightweight health check and current chunk count."""
    return {"ok": True, "chunks": agent.store.count()}


@app.post("/auth/register")
def register(request: AuthRegisterRequest) -> dict[str, object]:
    """Create one local account and return the signed-in session payload."""
    try:
        return auth_store.register_user(
            request.username,
            request.password,
            request.displayName,
            remember_me=request.rememberMe,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/auth/login")
def login(request: AuthLoginRequest) -> dict[str, object]:
    """Validate local credentials and return a fresh session token."""
    try:
        return auth_store.authenticate_user(request.username, request.password, remember_me=request.rememberMe)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/auth/me")
def auth_me(authorization: str | None = Header(default=None)) -> dict[str, object]:
    """Return the public profile of the current signed-in local user."""
    token = read_bearer_token(authorization)
    user = auth_store.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录状态已失效")
    return {"user": user}


@app.post("/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, object]:
    """Revoke the current signed-in session token."""
    token = read_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="未提供登录凭证")
    if not auth_store.revoke_token(token):
        raise HTTPException(status_code=401, detail="登录状态已失效")
    return {"ok": True}


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    category: str = Form("默认"),
    current_user: dict[str, str] = Depends(require_auth),
) -> dict[str, object]:
    """Upload a document and add its parsed chunks to the knowledge base."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return agent.upload_bytes(file.filename or "upload.pdf", content, category=category)


@app.get("/documents")
def list_documents(current_user: dict[str, str] = Depends(require_auth)) -> dict[str, object]:
    """List documents currently indexed in the local knowledge base."""
    documents = [document_summary_to_dict(item) for item in agent.list_documents()]
    return {"items": documents, "count": len(documents)}


@app.get("/categories")
def list_categories(current_user: dict[str, str] = Depends(require_auth)) -> dict[str, object]:
    """List knowledge-base categories currently available for upload and query."""
    categories = agent.list_categories()
    return {"items": categories, "count": len(categories)}


@app.post("/categories")
def add_category(request: CategoryRequest, current_user: dict[str, str] = Depends(require_auth)) -> dict[str, object]:
    """Create a new knowledge-base category for future uploads and filtering."""
    try:
        result = agent.add_category(request.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    categories = agent.list_categories()
    return {**result, "items": categories, "count": len(categories)}


@app.put("/categories/{category_name}")
def rename_category(
    category_name: str,
    request: CategoryRequest,
    current_user: dict[str, str] = Depends(require_auth),
) -> dict[str, object]:
    """Rename one knowledge-base category and update its existing documents."""
    try:
        result = agent.rename_category(category_name, request.name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    categories = agent.list_categories()
    return {**result, "items": categories, "count": len(categories)}


@app.delete("/categories/{category_name}")
def delete_category(category_name: str, current_user: dict[str, str] = Depends(require_auth)) -> dict[str, object]:
    """Delete one category and move its documents to the default category."""
    try:
        result = agent.delete_category(category_name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    categories = agent.list_categories()
    return {**result, "items": categories, "count": len(categories)}


@app.delete("/documents/{document_id}")
def delete_document(document_id: str, current_user: dict[str, str] = Depends(require_auth)) -> dict[str, object]:
    """Delete one indexed document and all of its local chunks."""
    result = agent.delete_document(document_id)
    if result["deletedChunks"] == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@app.put("/documents/{document_id}")
def update_document(
    document_id: str,
    request: DocumentUpdateRequest,
    current_user: dict[str, str] = Depends(require_auth),
) -> dict[str, object]:
    """Update one indexed document's display name and category."""
    try:
        return agent.update_document(document_id, request.source, request.category)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/query")
def query(request: QueryRequest, current_user: dict[str, str] = Depends(require_auth)) -> dict[str, object]:
    """Answer a query using local retrieval and optional online fallback."""
    response = agent.query(
        query=request.query,
        use_online_fallback=request.useOnlineFallback,
        user_id=request.userId,
        category=request.category,
    )
    return query_response_to_dict(response)


@app.post("/query/stream")
def stream_query(request: QueryRequest, current_user: dict[str, str] = Depends(require_auth)) -> StreamingResponse:
    """Stream one grounded answer so the frontend can render it incrementally."""

    def generate():
        """Yield SSE frames for metadata, answer deltas, completion, and error cases."""
        try:
            for event in agent.stream_query(
                query=request.query,
                use_online_fallback=request.useOnlineFallback,
                user_id=request.userId,
                category=request.category,
            ):
                yield sse_event(str(event["event"]), dict(event["data"]))
        except Exception as exc:  # pragma: no cover - defensive API guard
            yield sse_event("error", {"detail": str(exc)})

    return StreamingResponse(generate(), media_type="text/event-stream")
