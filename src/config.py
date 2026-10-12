"""Application configuration and settings management."""

import os
from pathlib import Path
from typing import Dict, List, Set
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine base repository root directory
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Global configuration settings for Fintech CodeGraph RAG."""

    model_config = SettingsConfigDict(
        env_file=None if os.environ.get("CODEGRAPH_SERVERLESS") == "1" else str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base paths
    base_dir: Path = BASE_DIR
    sample_codebase_dir: Path = BASE_DIR / "data" / "sample_codebase"
    vector_db_path: Path = BASE_DIR / "data" / "vector_store"
    graph_store_path: Path = BASE_DIR / "data" / "graph_index" / "codebase_graph.json"
    bm25_store_path: Path = BASE_DIR / "data" / "bm25_index" / "bm25_index.pkl"
    telemetry_log_dir: Path = BASE_DIR / "telemetry_logs"

    # LLM Settings
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY", repr=False, exclude=True)
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")

    # Finite Ollama network waits; not a total query deadline.
    ollama_connect_timeout: float = Field(
        default=5.0, alias="OLLAMA_CONNECT_TIMEOUT",
        gt=0, allow_inf_nan=False,
    )
    ollama_read_timeout: float = Field(
        default=180.0, alias="OLLAMA_READ_TIMEOUT",
        gt=0, allow_inf_nan=False,
    )

    # Embeddings & Reranker
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5", alias="EMBEDDING_MODEL")
    reranker_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2", alias="RERANKER_MODEL")

    # Security & RBAC Configuration
    default_tenant_id: str = Field(default="fintech-pk-corp", alias="DEFAULT_TENANT_ID")
    allowed_roles: List[str] = ["Junior Dev", "Senior Dev", "Security Lead"]
    api_role_tokens: Dict[str, str] = Field(
        default_factory=dict,
        alias="API_ROLE_TOKENS",
        repr=False,
        exclude=True,
    )

    # Security levels hierarchy and role clearance
    # Levels: public < internal < confidential < restricted
    role_clearance: Dict[str, Set[str]] = {
        "Junior Dev": {"public", "internal"},
        "Senior Dev": {"public", "internal", "confidential"},
        "Security Lead": {"public", "internal", "confidential", "restricted"},
    }

    # Path pattern rules for security classification
    security_path_rules: Dict[str, str] = {
        "secrets/": "restricted",
        "auth/": "confidential",
        "config/settings.py": "confidential",
        "integrations/": "internal",
        "api/": "internal",
        "services/": "internal",
        "db/": "internal",
        "utils/": "internal",
    }

    # API and Server
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    def ensure_directories(self) -> None:
        """Create necessary directories if they do not exist."""
        self.sample_codebase_dir.mkdir(parents=True, exist_ok=True)
        self.vector_db_path.mkdir(parents=True, exist_ok=True)
        self.graph_store_path.parent.mkdir(parents=True, exist_ok=True)
        self.bm25_store_path.parent.mkdir(parents=True, exist_ok=True)
        self.telemetry_log_dir.mkdir(parents=True, exist_ok=True)


# Global singleton settings instance
settings = Settings()
if os.environ.get("CODEGRAPH_SERVERLESS") != "1":
    settings.ensure_directories()
