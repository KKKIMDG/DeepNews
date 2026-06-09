# DeepNews Analyzer

네이버 뉴스 페이지에서 기사 URL을 로컬 백엔드로 보내고, 분석 결과를 크롬 확장 프로그램의 사이드 패널과 기사 페이지 팝업에 표시하는 MV3 기반 프로젝트입니다.

## 구조

- `src/content/content-script.js`: 기사 제목과 본문을 추출하고, 핵심 키워드를 본문에 하이라이트합니다.
- `src/background/service-worker.js`: 메시지를 받아 키워드 분석, 백엔드 호출, 스토리지 저장을 처리합니다.
- `src/background/api-client.js`: 로컬 백엔드 `http://127.0.0.1:8000/api/v1/news/analyze` 연동 포인트입니다. 실패 시 목업 응답으로 대체합니다.
- `src/panel/*`: 로그인/회원가입 UI와 키워드, 그래프, 요약, 추천 기사, 광고성 판별 결과를 보여주는 사이드 패널 UI입니다.
- `src/shared/constants.js`: 메시지 타입과 스토리지 키 상수입니다.

## 실행

1. 크롬에서 `chrome://extensions`로 이동합니다.
2. `개발자 모드`를 켭니다.
3. `압축해제된 확장 프로그램을 로드`에서 이 폴더를 선택합니다.
4. 네이버 뉴스 기사 페이지를 열고 확장 프로그램 아이콘을 클릭해 사이드 패널을 엽니다.

## 현재 가정

- 대상 뉴스 도메인은 `https://news.naver.com/*` 입니다.
- 백엔드 API는 `POST http://127.0.0.1:8000/api/v1/news/analyze` 형태로 기사 URL을 받습니다.
- 현재 인증 API는 로컬 백엔드에 없으므로 개발용 계정 `test@gmail.com / 1234`로 로그인/회원가입을 처리합니다.
