# DeepNews 로컬 Airflow

Airflow 3.3.2의 standalone 개발 환경입니다. 스케줄러·API 서버·DAG processor를
한 컨테이너에서 실행합니다. 원격 운영 배포용 구성은 아닙니다.

## 하는 일

`deepnews_bigkinds_import` DAG는 **매시 정각** `airflow/inbox/`에 들어온 빅카인즈 엑셀(`*.xlsx`)을
추천 후보 기사로 DB에 넣습니다. 파일마다 `python -m backend.run_bigkinds_import --file <파일>`과
같은 코드(`parse_rows` → `import_bigkinds_articles`)를 실행합니다.

- 성공한 파일은 `inbox/processed/`, 형식 오류 등으로 실패한 파일은 `inbox/failed/`로 옮깁니다.
  실패 원인은 같은 폴더의 `<파일명>.error.txt`에 남습니다.
- DB에 연결하지 못하면 파일을 inbox에 그대로 두고 다음 실행에서 다시 시도합니다.
- 수정된 지 60초가 지나지 않은 파일(복사 중일 수 있음)과 Excel 잠금 파일(`~$*.xlsx`)은 건너뜁니다.
- 이미 DB에 있는 URL은 건드리지 않습니다(새 URL만 추가). 확장 프로그램으로 저장된 전체 본문을 보호하기 위해서입니다.
- **웹 수집(크롤링)과 AI 모델 추론은 하지 않습니다.** 네이버는 robots.txt와 약관으로 자동 수집을
  금지하므로 이전의 네이버 수집 DAG는 삭제했습니다.

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

DAG는 최초 생성 시 일시정지 상태이며, 과거 실행을 몰아서 수행하지 않습니다.

```bash
cp NewsResult_*.xlsx airflow/inbox/        # 빅카인즈에서 직접 내려받은 엑셀
docker compose -f airflow/compose.yaml exec airflow airflow dags unpause deepnews_bigkinds_import
docker compose -f airflow/compose.yaml exec airflow airflow dags trigger deepnews_bigkinds_import
```

조회:

```bash
docker compose -f airflow/compose.yaml exec airflow airflow dags list-import-errors
docker compose -f airflow/compose.yaml exec airflow airflow dags list-runs deepnews_bigkinds_import
```

중지 (저장 볼륨 유지):

```bash
docker compose -f airflow/compose.yaml stop
```

## 설정 참고

- backend/.env 및 루트 .env를 컨테이너 환경으로 읽습니다(루트 파일 우선).
  DB 연결값을 이미지나 DAG 코드에 넣지 않습니다. 기사 DB 스키마는 API를 한 번 실행해 미리 만들어 둡니다.
- `airflow/inbox`는 컨테이너의 `/opt/deepnews/inbox`에 쓰기 가능하게 마운트됩니다.
  Linux 호스트라면 컨테이너의 airflow 사용자(uid 50000)가 이 폴더에 쓸 수 있어야 합니다.
- 동시 실행 1개, 재시도 없음, 작업 제한 30분입니다.
- 로컬 venv와 별개로 컨테이너 내부 전용 Python venv(`/opt/deepnews-runtime/venv`)에서 실행합니다.
- 키워드는 빅카인즈가 제공한 키워드 컬럼을 그대로 사용하므로 형태소 분석기(Java/Mecab)가 필요 없습니다.
- 컴퓨터 절전/종료 또는 Docker 종료 시 스케줄은 실행되지 않습니다.
- UI는 127.0.0.1에만 공개됩니다.
