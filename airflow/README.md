# DeepNews 로컬 Airflow

Airflow 3.3.2의 standalone 개발 환경입니다. 스케줄러·API 서버·DAG processor를
한 컨테이너에서 실행합니다. 원격 운영 배포용 구성은 아닙니다.

## 실행

프로젝트 루트에서 Docker Desktop을 실행한 뒤:

```bash
docker compose -f airflow/compose.yaml up -d --build
```

- UI: http://localhost:8080
- 사용자: admin
- 생성된 비밀번호 확인 (공유하거나 커밋하지 마세요):

```bash
docker compose -f airflow/compose.yaml exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated
```

`deepnews_news_ingestion` DAG를 켜면 30분마다 AI 검색 기사 최대 5개를 수집합니다.
최초 생성 시 일시정지이며, 과거 실행을 몰아서 수행하지 않습니다.
수동 실행은 UI의 Trigger 또는 아래 명령을 사용합니다.

```bash
docker compose -f airflow/compose.yaml exec airflow airflow dags unpause deepnews_news_ingestion
docker compose -f airflow/compose.yaml exec airflow airflow dags trigger deepnews_news_ingestion
```

조회:

```bash
docker compose -f airflow/compose.yaml ps
docker compose -f airflow/compose.yaml exec airflow airflow dags list-import-errors
docker compose -f airflow/compose.yaml exec airflow airflow dags list-runs deepnews_news_ingestion
```

중지 (저장 볼륨 유지):

```bash
docker compose -f airflow/compose.yaml stop
```

## 동작과 설정

- backend/.env 및 루트 .env를 컨테이너 환경으로 읽습니다(루트 파일 우선).
  DB 연결값을 이미지나 DAG 코드에 넣지 않습니다. 기존 기사 DB 스키마가 필요합니다.
- Airflow 메타데이터와 로그는 airflow-home 볼륨, 수집 JSON/CSV는 news-output 볼륨에 보관됩니다.
- `compose.yaml`의 DEEPNEWS_QUERY, DEEPNEWS_LIMIT을 수정하고 `up -d`하면 반영됩니다.
- DAG의 schedule은 매 30분, 동시 실행은 1개, 실패 시 2분 간격 2회 재시도,
  작업 제한은 20분입니다. DB 쓰기까지 하나의 작업에서 완료합니다.
- 로컬 venv와 별개로 컨테이너 내부 전용 Python venv에서 배치를 실행합니다.
- 컨테이너에는 Java/Mecab이 없어 현재 Regex 키워드 추출을 사용합니다.
  로컬 Mecab 결과와 다를 수 있으며 운영 전 형태소 분석기 통일이 필요합니다.
- 현재 DAG는 **수집 및 DB 저장만** 합니다. AI 모델 추론·재학습은 실행하지 않습니다.
  모델과 실행 서버가 준비되면 저장 성공 뒤 분석 작업을 연결합니다.
- 컴퓨터 절전/종료 또는 Docker 종료 시 스케줄은 실행되지 않습니다.
- UI는 127.0.0.1에만 공개됩니다. 서버 배포 시 인증·메타데이터 DB 구성을 별도로 준비합니다.
