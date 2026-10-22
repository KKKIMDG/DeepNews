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

## 버튼 기반 범용 기사 분석 (feat/article-extractor)

1. 백엔드를 실행하고 `chrome://extensions`에서 확장 프로그램을 새로고침합니다.
2. 기사 상세 페이지에서 확장 아이콘을 눌러 패널을 열고 로그인합니다.
3. **현재 기사 분석**을 누르고 해당 사이트 접근 권한을 허용합니다.
4. 확장 프로그램은 현재 페이지 DOM의 복사본에서 제목과 본문을 추출하고,
   `{ url, title, content }`를 기존 `/api/v1/news/analyze`에 보냅니다.

페이지 방문·로그인만으로는 분석하지 않습니다. 사이트 접근 권한은 버튼을 누를 때
해당 origin에 대해서만 요청하며, 권한을 허용한 후에도 자동 전송하지 않습니다.
코드는 외부 CDN에서 실행하지 않고 Mozilla Readability 0.6.0을 로컬에 포함합니다.
원본: https://github.com/mozilla/readability/tree/0.6.0
라이선스: `src/vendor/readability/`.

- 일반 뉴스/스포츠는 기존 본문 선택자를 우선 사용하고 나머지는 Readability로 추출합니다.
- 본문은 100~100,000자, 제목은 최대 500자입니다. PDF·브라우저 내부 페이지·
  유료벽으로 가려진 본문은 지원하지 않으며 모든 사이트의 추출 정확도를 보장하지 않습니다.
- API 실패는 오류로 표시합니다. 백엔드 모델 미설치 시 placeholder 저장 정책은 유지합니다.
- 같은 URL의 저장된 본문과 새 본문이 다르면 409를 반환합니다. 자동 덮어쓰기와
  변경 기사 재분석 정책은 아직 제공하지 않습니다.
- 브라우저 제공 본문은 `extraData.content_origin=browser`로 기록합니다.
  현재 개발용 인증을 사용하는 실험 기능으로, 공개 서비스에는 실제 인증 및
  사용자 제공 본문의 신뢰·공유 정책이 추가로 필요합니다.
- 범용 페이지의 키워드 결과는 패널에서 확인할 수 있습니다. 페이지 본문 하이라이트는
  현재 네이버 본문 선택자가 있는 경우에만 지원합니다.

검증: Python `python -m unittest discover -s tests -v`.
JS 추출 테스트는 jsdom 26.1.0 설치 후 `node tests/test_article_extraction.cjs` 실행
(프로젝트 루트 기준, 외부 설치 경로는 NODE_PATH로 지정).
실제 모델·DB·크롬 권한 팝업을 포함한 통합 확인은 별도로 수행합니다.
