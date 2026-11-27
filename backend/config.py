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
    # Sentence embeddings for keyword context (intfloat/multilingual-e5-small, MIT).
    keyword_model_dir: Path = PROJECT_ROOT / "model" / "multilingual-e5-small"
    max_len: int = 512
    summary_max_tokens: int = 200
    keyword_limit: int = 8
    # When set, signup requires this code; used while the API is reachable from outside for team testing.
    signup_invite_code: str = ""
    # NAVER search API keys for the live 네이버 뉴스 검색 section; results are never stored.
    naver_client_id: str = ""
    naver_client_secret: str = ""
    # Words that never name an article's subject. Common but meaningful words (정부, 기업) are left to the IDF
    # weighting in crawl.service.select_keywords instead.
    keyword_stopwords: frozenset[str] = frozenset({
        "이번", "관련", "통해", "대한", "위한", "지난", "이날", "정도", "이후", "현재", "기준", "가장", "매우",
        "기자", "뉴스", "앵커", "제보", "무단", "전재", "재배포", "배포", "금지", "저작권",
        "오늘", "어제", "내일", "올해", "작년", "지난해", "내년", "당시", "최근", "전날", "이달", "지난달",
        "경우", "때문", "가운데", "가능", "필요", "상황", "부분", "내용", "사실", "결과", "이상", "이하", "수준",
        "모습", "사람", "의견", "입장", "설명", "시작", "진행", "예정", "확인", "거론", "아래", "위해",
        "이유", "자신", "영향", "제외", "자사", "본인", "내외", "취재",
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
