from fastapi import FastAPI

from .config import settings
from .database import ensure_schema
from .domains.analysis.router import router as analysis_router
from .domains.crawl.router import router as crawl_router
from .domains.news.router import router as news_router
from .domains.recommendation.router import router as recommendation_router
from .domains.analysis.service import AD_MODEL_READY, SUMMARY_MODEL_READY

ensure_schema()

app = FastAPI()
app.include_router(news_router)
app.include_router(crawl_router)
app.include_router(analysis_router)
app.include_router(recommendation_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "ad_model_ready": AD_MODEL_READY,
        "summary_model_ready": SUMMARY_MODEL_READY,
        "database_ready": bool(settings.database_url),
        "ad_model_path": str(settings.ad_model_dir),
        "summary_model_path": str(settings.summary_adapter_dir),
    }
