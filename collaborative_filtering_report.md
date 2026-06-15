# 협업 필터링 구현 진행 보고서

작성일: 2026-06-15
프로젝트 경로: `D:\Deepnews`
기준 브랜치: 최신 `origin/dev` 기반 통합 브랜치

## 1. 개요

본 문서는 DeepNews 프로젝트의 협업 필터링 추천 기능을 최신 `dev` 브랜치 구조에 맞춰 통합한 내용을 정리한 보고서이다. 최신 `dev`는 Python/FastAPI 백엔드 구조를 사용하므로, 기존 Java 기반 초안은 그대로 병합하지 않고 동일한 추천 개념을 `backend/domains/recommendation` 도메인으로 이식하였다.

구현 목표는 MIND 원본 ZIP/폴더 없이도 발표용으로 정상 동작하는 협업 필터링 데모를 제공하는 것이다. 실제 추천은 서비스 내 `news_interaction` 로그를 기반으로 동작하고, 데이터가 부족한 경우 키워드 유사도와 최신 뉴스 fallback을 사용한다.

## 2. 통합 방향

- 최신 `dev` 브랜치를 우선 기준으로 유지
- Java/Spring 파일은 병합하지 않고 Python/FastAPI 구조에 맞춰 재구성
- MINDlarge 원본 데이터는 Git에 포함하지 않도록 `.gitignore`에 제외 규칙 추가
- `/api/v1/news/analyze` 응답에 추천 결과가 포함되도록 연동
- 별도 추천 조회 및 상호작용 기록 API 추가

## 3. 주요 변경 파일

- `.gitignore`
- `backend/sql/001_schema.sql`
- `backend/main.py`
- `backend/domains/news/schemas.py`
- `backend/domains/news/router.py`
- `backend/domains/news/service.py`
- `backend/domains/recommendation/__init__.py`
- `backend/domains/recommendation/schemas.py`
- `backend/domains/recommendation/service.py`
- `backend/domains/recommendation/router.py`

## 4. 데이터베이스 설계

협업 필터링을 위해 `news_interaction` 테이블을 추가하였다.

저장되는 주요 정보는 다음과 같다.

- `client_user_id`: 브라우저 또는 사용자 단위 식별자
- `news_id`: 상호작용한 뉴스 ID
- `interaction_type`: `VIEW`, `CLICK`, `BOOKMARK`, `DISMISS`
- `weight`: 추천 점수 계산용 가중치
- `created_at`, `updated_at`: 상호작용 기록 시각

상호작용 가중치는 다음과 같이 설계하였다.

| 상호작용 | 가중치 | 의미 |
|---|---:|---|
| `VIEW` | 1 | 기사 조회 |
| `CLICK` | 3 | 추천 기사 클릭 |
| `BOOKMARK` | 5 | 높은 관심도 |
| `DISMISS` | 0 | 비관심 또는 추천 제외 |

## 5. 추천 알고리즘 구조

추천 로직은 `backend/domains/recommendation/service.py`에 분리하였다. 추천 결과는 다음 순서로 생성된다.

1. 사용자 기반 협업 필터링
   - 현재 사용자와 같은 기사를 본 다른 사용자를 찾는다.
   - 유사 사용자가 추가로 본 기사를 추천한다.

2. 기사 기반 협업 필터링
   - 현재 기사를 본 사용자들이 함께 본 다른 기사를 추천한다.

3. 키워드 유사도 fallback
   - 협업 필터링 데이터가 부족한 경우 `article_keyword` 정보를 이용해 유사 키워드 기사를 추천한다.

4. 최신 뉴스 fallback
   - 추천 후보가 여전히 부족하면 최신 뉴스 목록을 반환한다.

이 구조를 통해 MIND 원본 데이터가 없어도 발표용 추천 결과가 비어 있지 않도록 설계하였다.

## 6. API 설계

### 6.1 분석 응답 내 추천 포함

기존 분석 API는 유지하면서 추천 결과를 함께 반환한다.

```http
POST /api/v1/news/analyze
```

요청 예시:

```json
{
  "url": "https://news.naver.com/...",
  "clientUserId": "client-demo-user"
}
```

응답의 `recommendations` 필드에 추천 기사 목록이 포함된다.

### 6.2 추천 조회 API

```http
GET /api/v1/recommendations?newsId=1&clientUserId=client-demo-user&limit=5
```

응답 예시:

```json
{
  "items": [
    {
      "newsId": 2,
      "title": "추천 기사 제목",
      "url": "https://...",
      "score": 3.0,
      "reason": "Readers also viewed",
      "source": "ITEM_CF"
    }
  ]
}
```

### 6.3 사용자 상호작용 기록 API

```http
POST /api/v1/recommendations/interactions
```

요청 예시:

```json
{
  "clientUserId": "client-demo-user",
  "newsId": 2,
  "interactionType": "CLICK"
}
```

## 7. MIND 데이터셋 처리 방향

MINDlarge 원본 파일은 로컬에는 존재하지만 GitHub에는 올리지 않는다.

제외 대상:

- `MINDlarge_train/`
- `MINDlarge_dev/`
- `MINDlarge_test/`
- `MINDlarge_*.zip`

현재 통합본은 MIND 원본 데이터 없이도 동작하는 구조이다. 향후 MIND를 실제 학습에 활용할 경우, 별도 Python 배치 파이프라인에서 전처리 및 학습을 수행하고 결과만 DB 또는 파일로 export하는 방식이 적합하다.

## 8. 향후 계획

- 프론트엔드에서 `clientUserId`를 생성 및 저장하여 분석 요청과 추천 상호작용 API에 전달한다.
- MINDlarge 기반 SVD 또는 item-based CF 학습 파이프라인을 별도 배치로 구현한다.
- 추천 결과의 클릭률, 북마크율, 비관심 비율을 수집하여 추천 품질을 개선한다.
- 데이터가 부족한 초기 사용자에게는 키워드 유사도와 최신 뉴스 fallback을 함께 제공한다.
- 발표 이후에는 MIND 기반 오프라인 평가 지표인 HitRate@K, NDCG@K, MRR을 추가한다.
