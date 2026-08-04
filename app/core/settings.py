from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    # Core
    ENVIRONMENT: str = "local"
    DEMO_MODE: bool = False
    
    # Security
    ADMIN_API_KEY: str = ""
    CORS_ORIGINS: List[str] = ["*"]
    LOG_LEVEL: str = "INFO"
    ALLOW_SEED_ENDPOINT: bool = False

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536
    
    # Qdrant
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_NAME: str = "items_collection"
    
    # Upstash Redis
    UPSTASH_REDIS_REST_URL: str = ""
    UPSTASH_REDIS_REST_TOKEN: str = ""
    CACHE_TTL_SECONDS: int = 60

    # Timeouts
    QDRANT_TIMEOUT_SECONDS: float = 5.0
    REDIS_TIMEOUT_SECONDS: float = 2.0
    OPENAI_TIMEOUT_SECONDS: float = 5.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
