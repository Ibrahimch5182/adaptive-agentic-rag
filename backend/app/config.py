from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import json


class Settings(BaseSettings):
    # Core
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    ENVIRONMENT: str = "development"  # development | production
    ALLOWED_HOSTS: List[str] = ["*"]  # production: set to actual API hostname(s)

    # Phase 6: cookie security
    COOKIE_SECURE: bool = False  # must be True in production (HTTPS)
    COOKIE_SAMESITE: str = "lax"

    # Phase 2: async queue
    REDIS_URL: str = "redis://localhost:6379"

    # Phase 2: vector store
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""  # required for Qdrant Cloud / managed Qdrant
    QDRANT_COLLECTION: str = "contextguard_chunks"

    # Phase 2/6: file storage
    STORAGE_BACKEND: str = "local"  # local | s3
    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # Phase 6: S3-compatible storage (used when STORAGE_BACKEND=s3)
    S3_BUCKET: str = ""
    S3_REGION: str = ""
    S3_ENDPOINT_URL: str = ""  # optional: non-AWS S3-compatible endpoints
    # AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY are read by boto3 directly from the
    # environment (standard credential chain) — not duplicated as settings here.

    # Phase 2: embedding models
    DENSE_EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    SPARSE_EMBEDDING_MODEL: str = "Qdrant/bm25"
    DENSE_VECTOR_SIZE: int = 384
    MAX_TOKENS_PER_CHUNK: int = 512

    # Phase 3: retrieval
    RETRIEVAL_DENSE_K: int = 20
    RETRIEVAL_SPARSE_K: int = 20
    RETRIEVAL_FUSED_K: int = 20
    RERANK_TOP_K: int = 5       # final evidence chunks after reranking
    RERANKER_MODEL: str = "Xenova/ms-marco-MiniLM-L-6-v2"

    # Phase 4: agent bounds
    AGENT_MAX_ITERATIONS: int = 3
    # Small bounded increase (from 5/2) — a live 6-aspect question left 3 aspects uncovered
    # after one planning round, forcing the planner to compound 2 aspects into one query
    # (0 new chunks retrieved) because only 2 call slots remained. iterations/evidence unchanged.
    AGENT_MAX_RETRIEVAL_CALLS: int = 7
    AGENT_MAX_EVIDENCE_CHUNKS: int = 15
    AGENT_MAX_QUERIES_PER_ITERATION: int = 3

    # Phase 3: LLM generation
    GROQ_API_KEY: str = ""
    LLM_MODEL: str = "openai/gpt-oss-20b"
    LLM_MAX_TOKENS: int = 3072  # bounded ceiling; multi-aspect cited answers were hitting 1024 (finish_reason=length)

    @field_validator("CORS_ORIGINS", "ALLOWED_HOSTS", mode="before")
    @classmethod
    def parse_json_list(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v):
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("STORAGE_BACKEND")
    @classmethod
    def validate_storage_backend(cls, v):
        if v not in ("local", "s3"):
            raise ValueError("STORAGE_BACKEND must be 'local' or 's3'")
        return v

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()

if settings.STORAGE_BACKEND == "s3" and not settings.S3_BUCKET:
    raise RuntimeError("S3_BUCKET is required when STORAGE_BACKEND=s3")
