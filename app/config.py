"""Application settings.

`load_dotenv()` runs at import time, and LangChain reads LANGSMITH_* from the environment
when it is imported. This module must therefore be imported before any langchain or
langgraph module — see the first line of `app/api/main.py`.
"""

import os
import sys
from typing import Literal

import certifi
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

# macOS ships a Python without the system cert store wired up, so `requests` fails TLS
# verification against some APIs.
if sys.platform == "darwin":
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())


class Settings(BaseSettings):
    openai_api_key: str
    openai_model: str = "gpt-4.1"
    openai_temperature: float = 0.3

    aviationstack_api_key: str | None = None
    tavily_api_key: str | None = None

    database_url: str | None = None

    cors_origins_csv: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        validation_alias="CORS_ORIGINS",
    )
    chat_rate_limit: str = "20/minute"

    langsmith_tracing: bool = True
    langsmith_api_key: str | None = None
    langsmith_project: str = "voyanta-dev"
    environment: Literal["dev", "staging", "prod"] = "dev"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    recursion_limit: int = 25
    request_timeout: int = 60
    max_retries: int = 2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_csv.split(",") if o.strip()]

    @property
    def tracing_enabled(self) -> bool:
        return self.langsmith_tracing and bool(self.langsmith_api_key)


settings = Settings()  # type: ignore[call-arg]
