# DeepNews
# DeepNews

## MIND SVD Mock Recommendation Demo

This branch adds a capstone-friendly recommendation demo flow:

1. Collect Korean Naver News metadata with the official Naver News Search API.
2. Train a collaborative filtering model with MIND `behaviors.tsv` using SVD.
3. Map recommended MIND news IDs to collected Naver-style metadata for the UI.
4. Return only Korean news metadata to the client.

The MIND behavior log is not copied into DeepNews user logs. It is used only to prove the collaborative filtering pipeline and the backend/API flow during the demo.

### Environment

Create `.env` in the project root. Runtime files are written under `backend/runtime/recommendation` and are ignored by Git.

```text
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
MIND_TRAIN_DIR=D:\Deepnews\MINDlarge_train
RECOMMENDATION_RUNTIME_DIR=D:\Deepnews_codex_mind_svd\backend\runtime\recommendation
```

`DATABASE_URL` is optional for the recommendation demo endpoints. Database-backed news/analysis endpoints still require it.

### Build Demo Artifacts

```powershell
python -m pip install -r requirements.txt
python -m backend.run_recommendation_pipeline --per-keyword 100 --max-behaviors 100000 --components 64 --limit 10
```

Generated files:

```text
backend/runtime/recommendation/naver_news.json
backend/runtime/recommendation/mind_svd_model.pkl
backend/runtime/recommendation/mind_svd_stats.json
backend/runtime/recommendation/mind_naver_mapping.json
```

### Run API

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8011
```

Useful endpoints:

```text
GET  /health
POST /api/v1/recommendations/naver/collect
POST /api/v1/recommendations/mind-svd/build
POST /api/v1/recommendations/mind-svd/mapping/build
GET  /api/v1/recommendations/mind-svd/demo-user
GET  /api/v1/recommendations/mind-svd?user_id=U536528&limit=10
```

The recommendation response contains clickable Naver article URLs in each item.
