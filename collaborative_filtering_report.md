# 협업 필터링 구현 진행 보고서

작성일: 2026-06-15
프로젝트 경로: `D:\Deepnews`

## 1. 개요

본 보고서는 DeepNews 프로젝트에서 진행한 협업 필터링 추천 기능의 현재 구현 상태와 향후 개발 방향을 정리한 문서이다. 현재까지의 작업은 크게 서비스 로그 기반 협업 필터링 초안 구현과 MIND 데이터셋 기반 추천 모델 구조 검토로 나눌 수 있다.

협업 필터링 기능의 목표는 사용자의 기사 조회, 클릭, 북마크, 비관심 등의 행동 데이터를 기반으로 개인화된 뉴스 추천을 제공하는 것이다. 또한 MIND 데이터셋을 활용하여 추천 알고리즘을 학습 및 평가하고, 실제 서비스에서는 사용자 행동 로그 기반 추천과 결합하는 구조를 목표로 한다.

## 2. 현재 저장소 상태

현재 확인한 기준 저장소는 `D:\Deepnews`이다.

- 현재 브랜치: `Test`
- 추적 브랜치: `origin/test`
- 협업 필터링 관련 Java 백엔드 초안이 작업트리에 반영되어 있음
- MINDlarge 데이터셋이 로컬에 압축 및 압축 해제된 상태로 존재함
- 참고 가능한 별도 브랜치로 `codex/mind-svd-mock-recommendation`이 존재함

확인된 주요 MIND 데이터셋 경로는 다음과 같다.

- `MINDlarge_train/news.tsv`
- `MINDlarge_train/behaviors.tsv`
- `MINDlarge_dev/news.tsv`
- `MINDlarge_dev/behaviors.tsv`
- `MINDlarge_test/news.tsv`
- `MINDlarge_test/behaviors.tsv`

## 3. 현재까지 구현된 내용

현재 `Test` 브랜치 작업트리에는 Spring 백엔드 기반 협업 필터링 초안이 구현되어 있다. 주요 구현 파일은 다음과 같다.

- `backend/src/main/java/com/deepnews/domain/recommendation/service/RecommendationService.java`
- `backend/src/main/java/com/deepnews/domain/recommendation/repository/NewsInteractionRepository.java`
- `backend/src/main/java/com/deepnews/domain/recommendation/entity/NewsInteraction.java`
- `backend/src/main/java/com/deepnews/domain/news/service/NewsService.java`
- `backend/src/main/java/com/deepnews/domain/news/dto/AnalyzeArticleResponseDto.java`
- `backend/batch/sql/001_supabase_news_pipeline.sql`

### 3.1 사용자 행동 로그 기반 추천 구조

현재 구현은 실제 서비스 사용자의 행동 로그를 기반으로 추천 후보를 계산하는 구조이다. 사용자의 뉴스 상호작용을 `news_interaction` 테이블에 저장하고, 이를 기반으로 비슷한 사용자가 함께 본 기사를 추천한다.

지원하는 상호작용 유형은 다음과 같다.

- `VIEW`: 기사 조회
- `CLICK`: 추천 기사 클릭
- `BOOKMARK`: 기사 저장 또는 관심 표시
- `DISMISS`: 비관심 표시

각 상호작용에는 추천 점수 계산에 사용할 가중치가 부여된다.

| 상호작용 | 가중치 | 의미 |
|---|---:|---|
| `VIEW` | 1 | 기본 조회 행동 |
| `CLICK` | 3 | 추천 기사에 대한 적극적 관심 |
| `BOOKMARK` | 5 | 높은 관심도 |
| `DISMISS` | 0 | 추천 제외 또는 낮은 선호도 |

### 3.2 추천 서비스 분리

추천 로직은 `NewsService` 내부에 직접 구현하지 않고, 별도의 `RecommendationService`로 분리하는 방향으로 구성하였다.

이 구조의 장점은 다음과 같다.

- 뉴스 분석 로직과 추천 로직의 책임 분리
- 추천 알고리즘 교체 및 확장 용이
- MIND 기반 모델, 서비스 로그 기반 모델, 키워드 fallback 추천을 하나의 추천 서비스에서 조합 가능
- 향후 추천 API 분리 및 테스트 작성에 유리

### 3.3 추천 흐름

현재 추천 흐름은 다음 순서로 동작하도록 설계되어 있다.

1. 현재 사용자 ID가 존재하면 사용자 행동 이력 기반 추천을 우선 조회한다.
2. 추천 수가 부족하면 현재 기사 기준으로 같은 기사를 본 사용자들의 다른 기사 후보를 조회한다.
3. 여전히 부족하면 키워드 유사도 기반 추천으로 보완한다.
4. 사용자가 이미 본 기사는 추천 결과에서 제외한다.
5. `DISMISS` 등 가중치가 0인 상호작용은 추천 점수 계산에서 제외한다.

## 4. MIND 데이터셋 검토 내용

MIND 데이터셋은 Microsoft News Dataset으로, 사용자 뉴스 클릭 이력과 뉴스 메타데이터를 포함하고 있다. 본 프로젝트에서는 MINDlarge 버전을 로컬에 준비하였다.

MIND 데이터셋의 주요 파일은 다음과 같다.

- `news.tsv`: 뉴스 ID, 카테고리, 제목, 본문 요약, URL, 엔티티 정보 포함
- `behaviors.tsv`: 사용자 ID, 클릭 이력, 노출 기사, 클릭 여부 포함
- `entity_embedding.vec`: 뉴스 엔티티 임베딩
- `relation_embedding.vec`: 엔티티 관계 임베딩

협업 필터링 구현에서 가장 중요한 파일은 `behaviors.tsv`이다. 해당 파일을 통해 사용자별 클릭 기사 목록을 구성하고, 사용자-뉴스 상호작용 행렬을 만들 수 있다.

## 5. 참고 브랜치: MIND SVD 목업 구현

`codex/mind-svd-mock-recommendation` 브랜치에는 MIND 데이터셋 기반 SVD 추천 목업 구현이 존재한다.

주요 파일은 다음과 같다.

- `backend/domains/recommendation/mind_svd.py`
- `backend/domains/recommendation/service.py`
- `backend/domains/recommendation/router.py`
- `backend/domains/recommendation/mock_mapping.py`
- `backend/domains/recommendation/naver_collector.py`
- `backend/run_recommendation_pipeline.py`

해당 브랜치의 주요 기능은 다음과 같다.

- MIND `behaviors.tsv`를 chunk 단위로 읽어 사용자-뉴스 sparse matrix 생성
- `TruncatedSVD`를 활용한 latent factor 기반 추천 모델 학습
- 사용자 factor와 item factor를 계산하여 개인화 추천 생성
- MIND 뉴스 ID를 수집된 네이버 뉴스 메타데이터에 mock mapping
- `/api/v1/recommendations/mind-svd` 형태의 추천 API 제공

이 구현은 실제 서비스 통합보다는 MIND 기반 협업 필터링 알고리즘의 가능성을 검증하기 위한 목업에 가깝다. 다만 MIND 데이터셋 처리 방식, sparse matrix 구성 방식, SVD 학습 구조는 향후 정식 추천 파이프라인 설계에 참고할 수 있다.

## 6. 현재 구현의 한계

현재까지의 구현은 기능 방향을 확인하기 위한 초안 단계이며, 다음과 같은 한계가 있다.

- 현재 Java 백엔드 초안은 MIND 데이터셋을 직접 학습에 사용하지 않는다.
- MIND 기반 SVD 목업은 별도 브랜치에 있으며, 현재 Spring 백엔드 구조와 직접 통합되어 있지 않다.
- MIND 뉴스 ID와 실제 네이버 뉴스 URL은 직접 매칭되지 않아 mock mapping 또는 별도 매핑 전략이 필요하다.
- 현재 서비스 로그가 충분히 쌓이기 전까지는 순수 협업 필터링 추천 품질이 낮을 수 있다.
- Java 백엔드 초안에는 컴파일 정리와 인코딩 정리가 필요한 부분이 남아 있다.
- MINDlarge 데이터셋은 크기가 크기 때문에 요청 시점 실시간 처리 방식이 아니라 오프라인 배치 처리가 필요하다.

## 7. 향후 구현 계획

향후 협업 필터링 기능은 다음 순서로 구현하는 것이 적합하다.

1. 최신 기준 브랜치를 확정하고, Java 기반 서비스 추천 구조와 MIND SVD 목업 구조를 통합 가능한 방향으로 재정리한다.
2. MINDlarge 데이터셋을 별도 Python 배치 파이프라인에서 전처리하여 사용자-뉴스 상호작용 행렬을 생성한다.
3. Item-based collaborative filtering 또는 SVD 기반 추천 모델을 학습하고, HitRate@K, NDCG@K, MRR 등의 지표로 평가한다.
4. 학습 결과를 `recommendation_item_similarity` 또는 별도 추천 결과 저장소에 export한다.
5. Spring 백엔드에서는 사용자 행동 로그 저장, 추천 결과 조회, 분석 응답 내 추천 포함 기능을 담당하도록 정리한다.
6. 프론트엔드에서는 사용자 식별자 생성, 추천 노출, 클릭, 북마크, 비관심 이벤트 전송 기능을 연동한다.
7. 서비스 초기에는 키워드 유사도 추천을 fallback으로 제공하고, 행동 로그가 충분히 쌓이면 협업 필터링 추천 비중을 높인다.

## 8. 최종 방향

최종 구조는 MIND 데이터셋을 오프라인 학습 및 평가용으로 활용하고, 실제 서비스에서는 사용자 행동 로그 기반 협업 필터링을 중심으로 운영하는 하이브리드 추천 구조가 적합하다.

추천 시스템의 역할 분리는 다음과 같이 정리할 수 있다.

- MIND 데이터셋: 추천 알고리즘 학습 및 오프라인 평가
- Python 배치 파이프라인: 대용량 데이터 전처리, 모델 학습, 추천 결과 export
- Spring 백엔드: 사용자 행동 로그 저장, 추천 API 제공, 분석 응답과 추천 결과 통합
- 프론트엔드: 사용자 행동 이벤트 수집 및 추천 결과 표시
- DB: 뉴스 데이터, 사용자 상호작용, 추천 결과, 모델 실행 이력 저장

따라서 협업 필터링 구현은 단순히 추천 쿼리 하나를 추가하는 작업이 아니라, 데이터 수집, 모델 학습, 백엔드 API, 프론트 이벤트 수집까지 연결되는 추천 시스템 아키텍처로 확장되어야 한다.
