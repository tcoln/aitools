import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "AI Tools - MCP Chat"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite+aiosqlite:///./data/app.db"

    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    LLM_PROVIDER: str = "openai"
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o"
    OLLAMA_API_BASE: str = "http://localhost:11434"

    DATA_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()