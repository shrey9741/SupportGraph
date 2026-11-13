"""Settings loaded from environment (.env at the project root)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    # "stub" = offline keyword baseline (no API key), "groq" = real model
    llm_provider: str = "stub"
    llm_model: str = "openai/gpt-oss-20b"
    groq_api_key: str | None = None
    confidence_threshold: float = 0.75
    refund_auto_limit_usd: float = 200.0
    max_llm_attempts: int = 3
    database_path: str = str(ROOT / "support_graph.db")
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")


def get_settings() -> Settings:
    """Read env at call time so tests and scripts can override values."""
    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "stub").lower(),
        llm_model=os.getenv("LLM_MODEL", "openai/gpt-oss-20b"),
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.75")),
        refund_auto_limit_usd=float(os.getenv("REFUND_AUTO_LIMIT_USD", "200")),
        max_llm_attempts=int(os.getenv("MAX_LLM_ATTEMPTS", "3")),
        database_path=os.getenv("DATABASE_PATH", str(ROOT / "support_graph.db")),
        cors_origins=tuple(
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if o.strip()
        ),
    )
