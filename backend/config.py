from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL_DIR = PROJECT_ROOT / "backend" / "sql"

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str
    ad_model_dir: Path = PROJECT_ROOT / "model" / "ad_model"
    summary_model_dir: Path = PROJECT_ROOT / "model" / "kobart_summary_final_v2"
    max_len: int = 512
    summary_max_tokens: int = 200
    keyword_limit: int = 8
    # When set, signup requires this code; used while the API is reachable from outside for team testing.
    signup_invite_code: str = ""
    # NAVER search API keys for the live 네이버 뉴스 검색 section; results are never stored.
    naver_client_id: str = ""
    naver_client_secret: str = ""
    keyword_stopwords: frozenset[str] = frozenset({
        "이번",
        "관련",
        "통해",
        "대한",
        "위한",
        "지난",
        "이날",
        "정도",
        "이후",
        "현재",
        "기준",
        "가장",
        "매우",
    })


def resolve_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return database_url

    host = os.getenv("DB_HOST", "").strip()
    if host:
        port = os.getenv("DB_PORT", "5432").strip() or "5432"
        name = os.getenv("DB_NAME", "postgres").strip() or "postgres"
        user = os.getenv("DB_USER", "").strip()
        password = os.getenv("DB_PASSWORD", "").strip()
        sslmode = os.getenv("DB_SSLMODE", "require").strip() or "require"
        auth = f"{user}:{password}@" if user else ""
        return f"postgresql://{auth}{host}:{port}/{name}?sslmode={sslmode}"

    raise RuntimeError("DATABASE_URL is required. Put it in the environment or .env file.")


settings = Settings(
    database_url=resolve_database_url(),
    signup_invite_code=os.getenv("SIGNUP_INVITE_CODE", "").strip(),
    naver_client_id=os.getenv("NAVER_CLIENT_ID", "").strip(),
    naver_client_secret=os.getenv("NAVER_CLIENT_SECRET", "").strip(),
)
