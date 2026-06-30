from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("KNOWLEDGE_AGENT_DATA_DIR", "data"))
    upload_dir: Path = Path(os.getenv("KNOWLEDGE_AGENT_UPLOAD_DIR", "data/uploads"))
    index_path: Path = Path(os.getenv("KNOWLEDGE_AGENT_INDEX_PATH", "data/index/store.json"))
    users_path: Path = Path(os.getenv("KNOWLEDGE_AGENT_USERS_PATH", "data/auth/users.json"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "900"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "120"))
    top_k: int = int(os.getenv("TOP_K", "5"))
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.72"))
    search_endpoint: Optional[str] = os.getenv("SEARCH_ENDPOINT")
    search_api_key: Optional[str] = os.getenv("SEARCH_API_KEY")
    search_timeout_seconds: float = float(os.getenv("SEARCH_TIMEOUT_SECONDS", "8"))
    llm_endpoint: Optional[str] = os.getenv("LLM_ENDPOINT")
    llm_api_key: Optional[str] = os.getenv("LLM_API_KEY")
    llm_provider: str = os.getenv("LLM_PROVIDER", "local")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))


def get_settings() -> Settings:
    """Load runtime settings from environment variables and .env."""
    return Settings()
