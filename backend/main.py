import logging

from fastapi import FastAPI
from sqlalchemy import text

from .config import settings
from .database import engine, ensure_schema
from .domains.auth.router import router as auth_router
from .domains.collect.router import router as collect_router
from .domains.personalization.router import router as personalization_router
from .domains.naver_search.router import router as naver_search_router
from .domains.news.router import router as news_router
from .domains.analysis.service import AD_MODEL_READY, SUMMARY_MODEL_READY

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ensure_schema()

app = FastAPI()
app.include_router(news_router)
app.include_router(auth_router)
app.include_router(personalization_router)
app.include_router(naver_search_router)
app.include_router(collect_router)


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        database_ready = True
    except Exception:
        logging.getLogger(__name__).exception("DB 연결 확인 실패")
        database_ready = False
    return {
        "status": "ok" if database_ready and AD_MODEL_READY and SUMMARY_MODEL_READY else "degraded",
        "ad_model_ready": AD_MODEL_READY,
        "summary_model_ready": SUMMARY_MODEL_READY,
        "database_ready": database_ready,
        "signup_invite_required": bool(settings.signup_invite_code),
        "naver_search_ready": bool(settings.naver_client_id and settings.naver_client_secret),
    }
