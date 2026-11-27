# DeepNews

뉴스 기사를 읽는 동안 Chrome 사이드 패널에서 **광고성 기사 여부**(RoBERTa)와 **요약**(KoBART)을 보여 주고,
읽은 기록과 관심 키워드로 **비슷한 다른 기사를 추천**하는 프로젝트입니다.

## 구성

| 폴더 | 내용 |
| --- | --- |
| `frontend/` | Chrome 확장 프로그램(MV3). 사용자가 버튼을 누를 때만 현재 탭의 기사 본문을 추출해 API로 보냅니다. |
| `backend/` | FastAPI 서버와 배치 도구. 도메인별 `router / schemas / service` 구조입니다. [backend/README.md](backend/README.md) |
| `ai/` | 학습·데이터 준비 스크립트(광고 분류기, KoBART 요약). 백엔드는 이 코드를 import하지 않습니다. |
| `airflow/` | 빅카인즈 엑셀 inbox를 매시 DB로 가져오는 로컬 Airflow. [airflow/README.md](airflow/README.md) |
| `deploy/` | GPU 서버에서 API를 재시작하는 스크립트 |
| `tests/` | Python 단위 테스트와 브라우저 추출 테스트(jsdom) |

모델 가중치는 git에 포함되지 않습니다. `model/ad_model/`, `model/kobart_summary_final_v2/`에 둡니다.

## 실행

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                     # 서버와 같은 고정 버전(Python 3.10 기준)
# .env 또는 backend/.env에 DATABASE_URL 설정
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

확장 프로그램: `chrome://extensions` → 개발자 모드 → "압축해제된 확장 프로그램을 로드" → `frontend/` 선택.
API 주소는 `http://127.0.0.1:8000/api/v1`입니다(GPU 서버 사용 시 SSH 터널로 이 포트를 연결).

## 테스트

```bash
DATABASE_URL=postgresql://x@localhost/x python -m unittest discover -s tests -v   # DB·모델 없이 실행
npm ci && node tests/test_article_extraction.cjs                                  # jsdom 필요
```

GitHub Actions(`.github/workflows/tests.yml`)가 push마다 같은 테스트를 실행합니다.

## 기사 데이터 출처와 정책

- **네이버 뉴스 자동 수집은 하지 않습니다.** 네이버 뉴스의 robots.txt는 모든 봇을 막고, 약관도 자동 수집을
  금지합니다. 이전의 네이버 수집 배치·Airflow DAG·서버 크롤링 API는 삭제했습니다.
- 사용자가 직접 연 기사는 확장 프로그램이 **사용자의 브라우저에서** 본문을 추출해 보냅니다. 서버는 기사 URL에 접속하지 않습니다.
- 추천 후보 기사는 **빅카인즈(한국언론진흥재단)** 에서 사람이 직접 내려받은 엑셀로 넣습니다.
  저작권 때문에 본문은 앞 200자만 있으므로 `content_partial`로 표시되고, 분석은 사용자가 그 기사를 열었을 때 이뤄집니다.

  ```bash
  python -m backend.run_bigkinds_import --file NewsResult_*.xlsx --dry-run   # 확인만
  python -m backend.run_bigkinds_import --file NewsResult_*.xlsx            # 새 URL만 추가
  ```

- `ai/step2_crawl.py`(라벨링용 본문 수집)는 사이트별 robots.txt를 확인하고 프로젝트를 밝히는 User-Agent로
  천천히 요청합니다. 허용되지 않은 사이트는 건너뜁니다.

## 학습

```bash
pip install -r requirements-ml.txt
python ai/train_ad_classifier.py                                   # 학습/검증/테스트 분할, 테스트 세트로만 최종 보고
python ai/train_kobart_summary.py --data ./output/summary.jsonl    # {text, summary} JSONL
```
