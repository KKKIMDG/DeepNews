# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Global Development Instructions

## 1. Communication
- 모든 답변과 작업 결과는 한국어로 작성한다.
- 코드의 함수명, 변수명, 기술 용어는 필요하면 영어를 사용한다.
- 코드 변경 시 변경 이유와 영향을 한국어로 설명한다.

## 2. Project Structure
- 이 폴더(`C:\ff`)는 DeepNews 저장소(`https://github.com/KKKIMDG/DeepNews.git`)의 `dev` 브랜치이다.
- 영역은 `backend/`(FastAPI·배치), `frontend/`(Chrome 확장), `ai/`(학습 스크립트), `airflow/`(수집 스케줄)로 나뉜다. 요청과 관련 없는 영역은 명시적인 요청 없이 수정하지 않는다.
- 백엔드 기능은 기존 `backend/domains/<도메인>/` 구조(router / schemas / service)를 따른다.
- 모델 가중치와 압축파일은 `model/`·루트 `*.zip`에 두며 git에 커밋하지 않는다(gitignore됨).
- GPU 서버 작업은 `~/deepnews` 안에서만 하며, GPU는 지정된 MIG 슬롯 하나만 사용한다(아래 "GPU 서버" 참고).

## 3. Development Workflow
- 작업 시작 전 프로젝트 구조와 기존 코드를 분석한다.
- 복잡한 작업은 먼저 구현 계획을 작성한다.
- 기존 기능과 코드 스타일을 최대한 유지한다.
- 불필요한 라이브러리 설치나 대규모 리팩터링을 피한다.
- 기존 파일을 삭제하거나 주요 설정을 변경하기 전 확인한다.

## 4. Code Quality
- 가독성 및 유지보수성을 우선한다.
- 중복 코드를 최소화한다.
- 환경변수와 민감한 인증정보를 코드에 하드코딩하지 않는다.
- 필요한 경우 오류 처리와 입력값 검증을 구현한다.
- 코드 주석은 복잡한 로직을 설명할 때만 작성한다.

## 5. Testing
- 구현 후 가능한 범위에서 테스트를 실행한다.
- 오류가 발생하면 원인을 분석하고 수정한다.
- 테스트하지 못한 부분은 명확히 알린다.
- 작업 완료 시 변경 파일과 검증 결과를 요약한다.

## 6. Git
- .env, API 키, 비밀번호 등 민감정보를 커밋하지 않는다.
- 명시적인 요청 없이 git push를 실행하지 않는다.
- 다른 작업의 변경 사항을 임의로 되돌리지 않는다.
- 커밋은 사용자가 요청한 경우에만 수행한다.

## 7. Response Format
작업 완료 시 다음 순서로 보고한다.

1. 작업 요약
2. 수정한 파일
3. 주요 변경 사항
4. 테스트 결과
5. 남은 문제 또는 주의사항

---

# DeepNews 프로젝트

뉴스 기사를 크롤링·키워드 추출하고, 광고성 판별(RoBERTa)과 요약(KoBART)을 수행해 Chrome 확장 프로그램 사이드 패널에 보여주는 프로젝트. 작업 브랜치는 `dev`.

## 명령어

모든 명령은 **프로젝트 루트**에서 실행한다 (`backend`는 패키지로 import되며 상대 import를 사용).

```bash
pip install -r requirements.txt          # 로컬 venv: .venv/ (gitignore됨)
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# 테스트는 실제 DB에 연결하지 않지만 DATABASE_URL이 설정돼 있어야 import된다 (.env가 없으면 더미 값으로 충분)
python -m unittest discover -s tests -v                                   # 전체 Python 테스트
python -m unittest tests.test_browser_analysis.BrowserAnalysisTests.test_request_validation -v  # 단일 테스트
npm install && npm run test:js           # JS 추출 테스트 (jsdom 26.1.0)

python -m backend.run_bigkinds_import --file NewsResult_*.xlsx [--dry-run]  # 빅카인즈 엑셀 → 추천 후보 기사
python -m backend.run_bigkinds_import --inbox airflow/inbox                # 폴더의 엑셀을 모두 import 후 processed/·failed/로 이동
python -m backend.run_analysis --limit 20                                 # 전체 본문이 있는 미분석 기사 배치 분석 (모델 필요)

docker compose -f airflow/compose.yaml up -d --build                      # 로컬 Airflow (http://localhost:8080)
```

린터/빌드 설정은 없다. `requirements.txt`는 GPU 서버 lock에 맞춘 Python 3.10 기준 고정 버전이며(torch 2.5.1은 3.13 휠이 없다), `ai/` 학습 스크립트용은 `requirements-ml.txt`. CI는 `.github/workflows/tests.yml`. 프론트엔드는 빌드 없이 `chrome://extensions` → 개발자 모드 → `frontend/` 폴더를 "압축해제된 확장 프로그램"으로 로드한다.

## 환경

- `backend/config.py`가 루트 `.env`, `backend/.env` 순으로 로드한다. `DATABASE_URL` 또는 `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`/`DB_SSLMODE`(기본 `require`)가 필수이며, 없으면 `backend.config` import 시점에 `RuntimeError`가 난다.
- 모델은 git에 포함되지 않으며 `model/`(gitignore) 아래에 둔다: `model/ad_model/`(RobertaForSequenceClassification), `model/kobart_summary_final_v2/`(BartForConditionalGeneration). 경로는 `Settings.ad_model_dir` / `Settings.summary_model_dir`. 모델 config는 transformers 5.x로 저장되었다.
- 키워드 형태소 분석기는 Mecab → Okt → Regex 순으로 폴백한다(`get_konlpy_analyzer`). Java/Mecab이 없는 환경에서는 Regex를 쓰므로 로컬 결과와 다를 수 있다.

## 아키텍처

### 요청 흐름 (실시간 분석)
1. 확장 프로그램(`frontend/`, MV3): 사용자가 패널의 **현재 기사 분석** 버튼을 누를 때만 동작. 해당 origin 권한을 그때 요청하고, `content/extract-article.js`가 DOM **복사본**에서 제목·본문·발행 시각을 추출(네이버 선택자 우선, 그 외 로컬 번들된 Readability 0.6.0. 언론사 본문 상자(`#news-contents`, `#CmAdContent` 등, 우선순위 순)가 있으면 Readability 결과가 그 글자 2-gram의 절반도 담지 못하거나 본문 상자보다 2배 넘게 길 때 본문 상자를 쓴다 — YTN의 '실시간 랭킹', 뉴스핌의 '베스트 기사' 전문이 섞이는 문제 대응)한 뒤 `background/api-client.js`가 `POST /api/v1/news/analyze`로 `{url, title, content, publishedAt}`를 로그인 토큰(`Authorization: Bearer`)과 함께 보낸다. 모든 API 호출은 `api-client.js`(base `http://127.0.0.1:8000/api/v1`)에 모여 있다.
   - service worker는 분석·팝업 상태를 **탭별로** `chrome.storage.session`(`deepnews.tabAnalysis.<tabId>` 등)에 두고, 패널이 보고 있는 탭(`deepnews.activeTabId`)의 상태만 `storage.local`의 `STORAGE_KEY`로 복사한다. 패널은 이 값을 그린다. 분석 요청에 tabId를 넘기면 그 탭이 현재 탭이 된다.
   - 메시지 발신자 검증: 확장 프로그램 페이지(`chrome-extension://<id>/` URL)에서 온 메시지만 처리하고, content script에서는 `OVERLAY_CLOSED`만 받는다. 토큰은 영속 로그인을 위해 `storage.local`에 두며 content script는 읽지 않는다.
   - 패널은 로그아웃 상태에서 캐릭터 '딥이'(`panel/mascot.js`, 인라인 SVG)의 인사와 2단계 회원가입(계정 → 관심 분야·키워드)을 보여 주고, 로그인하면 분석·맞춤·설정 탭으로 나뉜다. 애니메이션은 설정의 "캐릭터 애니메이션"(`deepnews.motion`, 미설정 시 OS의 동작 줄이기 설정을 따름)으로 끄며, 꺼지면 `:root[data-motion="off"]`가 모든 animation/transition을 없앤다. 관심 분야 코드 목록은 `constants.js::INTEREST_TOPICS`와 백엔드 `TOPIC_LABELS`가 같아야 한다.
   - content script의 하이라이트는 DOM API로만 `<mark>`를 넣고(`innerHTML` 금지), 팝업은 closed shadow root를 모듈 변수로만 참조한다. 본문 영역은 네이버 선택자 → 일반 기사 선택자 → 텍스트가 가장 많은 블록 순으로 찾는다(YTN처럼 `<p>` 없이 한 `div`에 본문이 있는 사이트 대응).
   - 401이면 저장된 로그인을 지운다. 비밀번호 확인 실패(탈퇴·비밀번호 변경)는 그래서 403이다.
2. `domains/news/service.py::analyze_or_get`이 핵심 오케스트레이터:
   - **서버는 기사 URL에 접속하지 않는다.** 로그인과 브라우저 본문(`content`)이 필수이며, `prepare_browser_article`로 정제·키워드 추출만 한다. 서버 크롤링 경로(`/crawl/article`, URL만 받는 분석, `/news/crawl`)는 네이버 정책 위반·SSRF·공용 데이터 무단 덮어쓰기 문제로 삭제했다. 되살리지 않는다.
   - URL은 먼저 `crawl/extractor.py::canonical_article_url`로 정규화한다. 네이버 기사는 `?sid=`, `/article/`과 `/mnews/article/`, `read.naver?oid=&aid=` 형태를 모두 `https://n.news.naver.com/mnews/article/{oid}/{aid}` 하나로 맞춘다. 다른 사이트 URL은 그대로 둔다. 조회는 `repository.fetch_news_by_canonical_url`이 맡으며, 정규화 이전에 `?sid=`가 붙은 채 저장된 행도 찾는다. 이 접두어 조회는 네이버 호스트에만 적용한다. 다른 사이트는 쿼리가 기사를 구분하는 경우가 많기 때문이다.
   - 이미 분석 결과가 있는 기사(`is_reusable`: 분석 있음, `content_partial` 아님, `ad_probability ≥ 0`)는 브라우저 본문이 달라도 덮어쓰지 않고 `cached=True`로 반환한다. 응답의 `sharedFromOther`가 참이면 패널이 신고 버튼을 보여 준다. 서로 다른 사용자 신고가 `REANALYSIS_REPORTS`(3)건 쌓이면 `news_analysis`를 지우고 다음 제출 때 다시 분석한다(`news_report` 테이블, `003_news_report.sql`).
   - 빅카인즈 후보(`content_partial`)를 교체할 때는 제출 본문이 저장된 앞 200자와 맞는지(`matches_lead`, 글자 2-gram 포함률 ≥ 0.6) 확인하고, 맞지 않으면 409. 남의 후보 기사를 가짜 본문으로 선점하지 못하게 하려는 것이다.
   - 처리 순서: 세션 1에서 조회·스냅샷 → **세션 없이** 정제와 모델 추론(느린 추론이 DB 커넥션을 잡지 않게) → 세션 2에서 다시 조회(동시 요청이 먼저 끝났으면 그 결과 반환) → `news`·키워드·`news_analysis`를 `INSERT … ON CONFLICT`로 저장. `extraData`에는 `content_origin=browser`, `submitted_by`(사용자 id)를 기록하고 기존 메타데이터(빅카인즈 분류, 발행일)는 유지한다.
   - `analysis/service.py::analyze_article`은 모델이 없거나 GPU 대기열(동시 2건, 120초)이 차면 `AnalysisUnavailable`을 던지고 라우터가 503으로 바꾼다. placeholder 결과는 저장하지 않는다. 광고 임계값은 `AD_HIGH_THRESHOLD`(0.8)·`AD_REVIEW_THRESHOLD`(0.4) 한 곳에서 관리한다.
   - 마지막에 `personalize_response`가 읽은 기록을 남기고 `personalization.service.recommend`로 추천 기사를 만든다. 500 응답에는 내부 오류 내용을 넣지 않고 서버 로그(`logging`)에만 남긴다.

### 인증 / 개인화
- `domains/auth`: 이메일/비밀번호(scrypt) 회원가입과 로그인. 세션 토큰은 SHA-256 해시만 `user_session`에 저장하며 30일 뒤 만료된다. 엔드포인트에는 `get_current_user`(로그인 필수) 또는 `get_optional_user`(선택) 의존성을 쓴다. 탈퇴는 `DELETE /api/v1/auth/me`이며 비밀번호를 다시 받는다. 비밀번호가 틀리면 403을 돌려준다(401이면 확장 프로그램이 로그아웃해 버린다). 세션·읽은 기록·키워드 설정은 FK `on delete cascade`로 함께 지워지고, 공용 기사·분석 데이터는 남는다. 비밀번호 변경(`PUT /auth/password`)도 같은 이유로 틀리면 403이며, 현재 세션만 남기고 다른 세션은 끊는다. 로그인 실패는 이메일별 15분에 5회, 회원가입은 전체 시간당 30회로 제한한다(`auth/rate_limit.py`, 프로세스 메모리 기반이라 uvicorn 워커 1개 전제). scrypt는 동시에 4개까지만 계산한다.
- `domains/personalization`: `/api/v1/me/{profile,keywords,topics,settings,history,recommendations,export}`. `export`는 계정·관심사 설정·읽은 기록 전체를 JSON으로 돌려준다. 점수 계산은 DB 없이 테스트할 수 있도록 순수 함수인 `ranking.py`에 모아 두었다.
  - 점수 = 0.6×현재 기사 TF-IDF 코사인 + 0.4×관심 프로필 코사인 + 관심 키워드 보너스 + 관심 분야 보너스 + 최신성 보너스.
  - 관심 프로필은 읽은 기록으로 만들며, 반감기는 14일이고 여러 번 읽은 기사일수록 가중치가 커진다.
  - **콜드 스타트 보정**: 회원가입 요청(`topics`, `keywords`)이나 `PUT /me/topics`로 관심 분야(빅카인즈 대분류 8개, `ranking.TOPIC_LABELS`, 테이블 `user_interest_topic`)를 고른다. 가입 때 넣은 키워드는 관심 키워드(include)로 저장된다. 분야별 대표어(`ranking.topic_terms`, 분야 안 빈도×log lift 상위 25개, 프로세스 캐시 6시간)를 프로필에 `0.35×강도`로 섞고, 같은 분야 기사에는 `0.15×강도` 보너스를 준다. 강도 `topic_strength`는 읽은 기사 0건일 때 1.0이고 10건이면 0.5, 최소 0.3이다. 그래서 나중에 분야를 바꿔도 반영된다. 분야 기사는 키워드가 겹치지 않아도 후보로 들어온다(`repository.topic_news_ids`).
  - 패널의 분석 탭은 현재 기사의 추천을 언론사(`publisher`, 빅카인즈 `extraData.publisher`, 없으면 호스트명)별로 묶어 보여 준다. 묶음 순서는 각 언론사의 최상위 기사 순위를 따른다. 네이버 기사를 보고 있으면 service worker가 네이버 호스트 기사만 추천으로 남긴다.
  - 맞춤 피드(현재 기사 없음)에서는 같은 분야를 고를 때마다 0.06씩 깎아 한 분야가 목록을 독차지하지 않게 한다. 현재 기사의 관련 기사 목록은 관련도 순서를 유지한다.
  - 추천에서 빼는 것: 이미 읽은 기사, 제외 키워드가 든 기사, 사용자별 광고 확률 기준값(`app_user.ad_filter_threshold`, 1.0이면 필터 끔) 이상인 기사.
  - 같은 사건을 다룬 다른 언론사 기사(제목 2글자 묶음 Jaccard ≥ 0.25 또는 키워드 코사인 ≥ 0.9)는 추천 목록 안에서 하나만 남긴다. 현재 기사나 최근 읽은 기사와 같은 사건인 기사도 뺀다.
- 저장된 키워드에는 Regex 분석기가 남긴 잡음(`안경을`, `있다`)이 섞여 있다. 개인화 계층은 `ranking.normalize_term`으로 이를 정리해서 쓰며(조사 제거, 서술어·일반어 제외), 원본 `keyword` 테이블은 그대로 둔다.

### 백엔드 구조 (`backend/`)
- 라우트: `POST /api/v1/news/analyze`, `POST /api/v1/news/{id}/report`, `/api/v1/auth/*`, `/api/v1/me/*`, `GET /api/v1/naver/news`, `GET /api/v1/collect/candidates`, `/health`. `crawl`·`analysis` 도메인에는 라우터가 없고 텍스트 정제(`crawl/extractor.py`, 네트워크 코드 없음)와 모델 추론만 남아 있다.
- **import 시 부작용 주의**: `backend.main`을 import하면 `ensure_schema()`가 `backend/sql/*.sql` 중 `schema_migration` 테이블에 기록되지 않은 파일만 이름 순서대로 실행한다(advisory lock으로 직렬화). 기존 DB에서는 처음 한 번 전부 다시 실행되므로 각 파일은 계속 여러 번 실행해도 안전해야 한다(`if not exists`). 또 `domains/analysis/service.py` import 시 모델을 즉시 로드한다. 모델/torch가 없으면 `AD_MODEL_READY`/`SUMMARY_MODEL_READY=False`가 되고 분석 요청은 503이다. `/health`는 모델 상태와 DB 연결(`select 1`)을 보여 주며 서버 경로는 노출하지 않는다. `backend/__init__.py`는 `app`을 lazy하게 노출해 배치 도구 import가 API를 띄우지 않게 한다.
- DB 접근 경로가 두 가지다: API는 SQLAlchemy(`database.py`, `domains/news/models.py`, `repository.py`), 배치는 psycopg2 직접 사용(`batch/storage.py`). 스키마 변경 시 양쪽을 모두 맞춰야 한다.
- 테이블:
  - 공용 기사 데이터: `news`(url unique, 본문·키워드는 `article_data` jsonb), `keyword`, `article_keyword`, `news_analysis`(news_id unique)
  - 사용자 데이터(`002_personalization.sql`): `app_user`, `user_session`, `user_read_history`, `user_keyword_preference`. 관심 분야(`004_user_interest_topic.sql`): `user_interest_topic`. 신고(`003_news_report.sql`): `news_report`(news_id·user_id unique).
  - `news_analysis.is_clickbait`에는 실제로 광고 판별 결과(`is_ad`)가 저장된다. 광고 라벨 임계값은 `ad_label_for`(≥0.8 높음, ≥0.4 검토 필요, <0 미분석), `is_ad`는 ≥0.8.

### 기사 데이터 출처와 수집 정책
- **네이버 자동 수집 금지**: 2026-10-30에 확인한 결과, `search.naver.com`, `news.naver.com`, `n.news.naver.com`의 robots.txt가 모든 봇에 `Disallow: /`이다. AI·RAG 목적의 봇 접근도 명시적으로 금지되어 있다. 네이버 약관에도 자동화 수집 금지 조항이 있으며 학술 목적 예외는 없다.
  - 그래서 네이버 수집 배치(`run_ingestion`, `batch/pipeline.py`, 루트 `naver_news_pipeline.py`), 수집 DAG, 서버 크롤링 API를 모두 삭제했다. 네이버 기사는 사용자가 직접 연 페이지를 확장 프로그램으로 분석할 때만 들어온다.
  - 네이버 공식 검색 API도 후보 수집에 쓰지 않는다. NAVER API 이용약관(2026-10-07 개정) 검색 API 특약 2.2·2.3이 결과의 복사·저장·캐싱(파생물 포함), AI 입력·학습·평가, 순위·내용 수정을 금지한다. 허용되는 임시 보관은 기기 24시간, 서버 이력 조회용 21일까지다(2.4). 학술·비상업 예외는 없다(2026-11-03 원문 확인). 개발자센터 신규 신청은 2026-07-30에 마감됐고 이후는 NCP NAVER API HUB 약관을 따른다.
- **빅카인즈(한국언론진흥재단) 엑셀이 기사 후보의 정식 출처다.**
  - 사람이 웹에서 직접 내려받는다. 1회 최대 2만 건이고, 저작권 때문에 본문은 앞 200자만 들어 있다.
  - `batch/bigkinds.py`가 행을 파싱한다. `분석제외 여부`가 표시된 행과 URL이 없는 행은 건너뛰고, `뉴스 식별자`는 반드시 `dtype=str`로 읽는다.
  - `storage.import_bigkinds_articles`는 **새 URL만 추가**한다(`on conflict do nothing`). 확장 프로그램으로 저장된 전체 본문을 덮어쓰지 않기 위해서다.
  - URL은 `canonical_article_url`로 정규화해 저장한다(네이버 링크 행이 확장 프로그램 URL과 맞도록).
  - 가져온 행에는 `extraData.content_partial=true`가 붙는다. `fetch_unanalyzed_news`(배치 분석)는 이 행을 건너뛴다.
  - 사용자가 확장 프로그램으로 그 기사를 분석하면 `analyze_or_get`이 앞 200자 일치를 확인한 뒤 전체 본문으로 교체하고 분석한다. 이때 빅카인즈 분류(`category`, `publisher` 등)와 발행일은 유지된다.
  - KBS 등 일부 언론사는 headless(자동화) 브라우저에 기사 대신 "페이지를 찾을 수 없습니다"를 보여 준다. 일반 Chrome에서는 정상적으로 열린다. 자동화 테스트·시연에는 YTN·뉴스핌처럼 robots.txt가 기사 경로를 허용하고 headless에서도 열리는 사이트를 쓴다.
- 추천의 최신성 점수는 `publishedAt`(기사 발행일)을 기준으로 계산한다. 대량 import는 `created_at`이 모두 같기 때문이다.

### 배치 / Airflow
- `batch/analysis.py`(`run_analysis`): 전체 본문이 있는 미분석 기사와 예전 placeholder 결과(`ad_probability < 0`)를 한 건씩 분석·커밋한다. 모델이 없으면 시작하지 않고(종료 코드 2), 실패한 행은 기록 후 건너뛴다(종료 코드 1). 대기열은 `random()` 순서라 계속 실패하는 행이 맨 앞을 막지 않는다. `--mode placeholder`는 DB에 쓰지 않는 dry run이다.
- `batch/storage.py`는 `connect()` 컨텍스트로 커밋/롤백 후 연결을 항상 닫는다.
- `airflow/dags/deepnews_ingestion.py`(DAG id `deepnews_bigkinds_import`): 매시간 `airflow/inbox/`에 넣어 둔 빅카인즈 엑셀을 import하고 `processed/`·`failed/`로 옮긴다. 스크래핑과 AI 추론은 하지 않는다. 컨테이너 내부 전용 venv(`/opt/deepnews-runtime/venv`)를 사용한다.

### GPU 서버 (API 실행 환경)
- API는 여러 연구실이 함께 쓰는 GPU 서버에서 돈다. 접속 정보, 디렉터리 구성, GPU(MIG) 사용 규칙, 실행 방법은 저장소에 올리지 않는 `CLAUDE.local.md`에 있다(gitignore됨). 서버 작업 전에 반드시 읽는다.
- 재시작은 서버에서 `bash ~/deepnews/repo/deploy/start_api.sh`로 한다. tmux 세션 안의 uvicorn에 Ctrl+C를 보내면 세션 자체가 끝나므로 쓰지 않는다.

### 팀 테스트용 외부 공개 (임시)
- GPU 서버에는 포트를 열지 않는다. 로컬 PC의 SSH 터널(`127.0.0.1:8000`) 위에 Cloudflare 임시 터널(`cloudflared tunnel --url http://127.0.0.1:8000`)을 띄워 `https://*.trycloudflare.com` 주소를 받는다. 이 주소는 터널을 다시 띄울 때마다 바뀐다.
### 수집 도우미 (`frontend/src/collect/`, `domains/collect`)
- 패널 설정 탭의 "수집 도우미 열기"로 여는 확장 프로그램 페이지. `GET /api/v1/collect/candidates`(로그인 필요)가 본문이 없는 빅카인즈 후보(`content_partial`)를 언론사별 개수와 함께 발행일 역순으로 준다.
- 사용자가 "열기"나 "다음 기사 열기"를 **누를 때마다 기사 하나**를 백그라운드 탭으로 연다(`COLLECT_OPEN`). service worker가 그 탭의 로드 완료 때 `analyzeTab`을 한 번 돌리고, 성공하면 탭을 닫는다(옵션). 실패하면 사용자가 볼 수 있도록 탭을 남긴다. 동시 진행은 `COLLECT_LIMIT`(3)건이다. 요청·결과는 `storage.session`의 `deepnews.collectTabs`·`deepnews.collectResults`에 두고 `withCollectStorage`로 직렬화한다.
- 언론사 리디렉트에 대비해 후보 탭은 후보 URL로 제출한다(`analyzeTab(tabId, submitUrl)`). 서버의 앞 200자 일치 검사가 그대로 적용된다.
- "네이버 기사 열면 자동 분석"(`deepnews.naverAutoCollect`)을 켜면, 사용자가 직접 연 네이버 기사(`isNaverArticleUrl`)를 로드될 때 분석한다. 네이버 권한(`NAVER_NEWS_ORIGINS`)은 켤 때 받는다.
- **자동으로 여러 기사를 연달아 여는 기능(일괄 열기, 타이머, 다음 기사 자동 진행)은 넣지 않는다.** 그러면 사람이 연 페이지가 아니라 크롤링이 된다. 네이버 검색 API 결과를 수집 목록으로 쓰지 않는다(특약 2.3).

### 네이버 뉴스 검색 (`domains/naver_search`)
- 네이버 기사를 분석하면 패널이 `GET /api/v1/naver/news`(로그인 필요, `sort=sim|date`, 사용자당 10분에 60회)로 검색해 별도 블록에 보여 준다. 개인화는 **검색어에만** 넣는다: ① 기사 키워드 상위 2개 + 첫 관심 키워드(결과가 없으면 기사 키워드 3개로 다시 검색) ② 관심 키워드(수동 → 읽은 기록 → 관심 분야 순) 상위 3개를 각각 최신순 3건. 목록마다 검색어를 함께 표시한다. 키는 서버 `backend/.env`의 `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`이며 `/health`의 `naver_search_ready`로 확인한다. 키 값은 저장소에 적지 않는다.
- 검색 API 특약 때문에 결과는 DB·로그·`chrome.storage`에 남기지 않고(패널 메모리에만 있다), 모델이나 추천 점수에 넣지 않으며, 네이버가 준 순서·문구 그대로 보여 준다(`<b>` 태그와 HTML 엔티티만 정리). 언론사별 묶음, 중복 제거, 필터링을 이 블록에 적용하지 않는다. 출처(원문 호스트)와 원문 링크, "검색 결과 제공: NAVER" 표시를 유지한다. 이 블록과 문구는 네이버 기사를 보고 있을 때만 나온다.
- 제목 링크는 네이버가 호스팅하는 기사면 `n.news.naver.com`(`naverUrl`)으로, 아니면 원문으로 간다.

- 공개하는 동안 서버 `backend/.env`에 `SIGNUP_INVITE_CODE`를 둔다. 값이 있으면 회원가입에 초대 코드가 필요하고, `/health`의 `signup_invite_required`로 알 수 있다. 공개를 끝내면 줄을 지우고 API를 재시작한다. 코드 값과 공개 주소는 저장소에 적지 않는다.
- 확장 프로그램은 패널의 "서버 주소" 설정(`deepnews.apiBase`, 기본 `http://127.0.0.1:8000`)으로 API 주소를 바꾼다. manifest에 없는 서버는 저장할 때 그 origin 권한을 요청하고, 서버를 바꾸면 로그아웃한다(계정은 서버 DB에 그대로 있다).

### 기타 디렉터리
- `ai/`: 학습·데이터 준비 스크립트. 백엔드는 이 코드를 import하지 않으며, 모델 경로(`./model_ad` 등)도 백엔드 경로와 다르다.
  - `train_ad_classifier.py`: 70/15/15 층화 분할, 검증셋으로 epoch를 고르고 테스트셋 점수만 보고한다. `sample_bigkinds.py`가 광고 후보를 소비자 주제에서 뽑아 주제 편향 위험이 있어, 일반 기사도 같은 대분류 비율로 뽑는다(`bigkinds_csv/general/*.xlsx`가 있을 때).
  - `train_kobart_summary.py`: 배포 중인 KoBART 요약 모델 재현용. 하이퍼파라미터 일부는 `training_args.bin`에서 복원했고 나머지는 가정이다(파일 docstring 참고).
  - `step2_crawl.py`: robots.txt를 확인하고 프로젝트를 밝히는 User-Agent를 쓴다.
- `deploy/start_api.sh`: GPU 서버에서 API를 안전하게 (재)시작하고 `/health`를 기다린다.

### 테스트 작성 방식
테스트는 DB/모델 초기화를 피하려고 `backend` 패키지를 우회한다. `test_crawl_extractor.py`·`test_personalization.py`는 `importlib.util.spec_from_file_location`으로 모듈 파일을 직접 로드하고, `test_browser_analysis.py`는 `sys.modules`에 `backend.config`, `backend.database`, `analysis.service`, `auth.dependencies`, `personalization.service` 등을 stub으로 넣은 뒤 import한다. `news/service.py`에 새 의존성을 추가하면 이 stub 목록에도 넣어야 한다. 새 테스트도 같은 방식을 따라야 실제 DB 없이 실행된다.
