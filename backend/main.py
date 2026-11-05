import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from .config import settings
from .database import engine, ensure_schema
from .domains.auth.router import router as auth_router
from .domains.collect.router import router as collect_router
from .domains.personalization.router import router as personalization_router
from .domains.naver_search.router import router as naver_search_router
from .domains.news.router import router as news_router
from .domains.analysis import service as analysis_service
from .domains.analysis.service import AD_MODEL_READY, SUMMARY_MODEL_READY
from .domains.crawl import service as crawl_service
from .domains.personalization import service as personalization_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ensure_schema()

logger = logging.getLogger(__name__)
warm_up_done = threading.Event()


def warm_up() -> None:
    # First-use costs (JVM, CUDA, a corpus-wide query) would otherwise land on the first user's request.
    for name, step in (
        ("형태소 분석기", crawl_service.warm_up),
        ("분석 모델", analysis_service.warm_up),
        ("분야 대표어", personalization_service.warm_up),
    ):
        started = time.perf_counter()
        try:
            step()
            logger.info("예열 완료: %s (%.1f초)", name, time.perf_counter() - started)
        except Exception:
            logger.exception("예열 실패: %s", name)
    warm_up_done.set()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=warm_up, name="warm-up", daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)
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
        "warmed_up": warm_up_done.is_set(),
        "signup_invite_required": bool(settings.signup_invite_code),
        "naver_search_ready": bool(settings.naver_client_id and settings.naver_client_secret),
    }
