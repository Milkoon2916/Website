# 영어 학습자료 제작소 (통합판)

지문분석기 / 워크북 메이커 / O/X 리딩 워크북 / 단어장 퀴즈를 하나의 FastAPI 서버로 합친 버전입니다.

## 폴더 구조

```
app/
  main.py              앱 진입점, 모든 라우터 + 화면 연결
  models.py            DB 테이블 정의 (teachers, word_lists, words, students,
                        quiz_results, passages, materials)
  db.py                DB 조회/저장 로직 (정원 제한 체크 포함)
  limits.py            용량 제한값 (단어장 100개, 단어 5000개, 학생 100명)
  auth.py              PIN 해시, JWT, Gemini 키 암호화
  routes_auth.py        회원가입/로그인/로그아웃/내정보
  routes_words.py       단어장·단어·학생 관리, 결과 보기 (로그인 필요)
  routes_public.py      학생용 (링크+코드, 로그인 불필요)
  routes_generate.py    지문분석/워크북/OX 생성 + PDF 다운로드 (로그인 필요)
  prompts.py            3개 도구의 Gemini 시스템 프롬프트
  analysis_schema.py    지문분석 결과의 JSON 스키마 (기존 프로젝트에서 이식)
  llm.py                Gemini API 실제 호출
  pdf_render.py         PDF 렌더링 (나눔고딕 폰트 파일을 직접 번들해서 사용)
  templates/            PDF용 Jinja2 HTML 템플릿 (analysis/workbook/ox)
  assets/fonts/         번들된 나눔고딕 폰트 (Regular, Bold)
static/
  index.html            홈페이지 (로그인/회원가입 + 4개 도구 카드)
  vocabulary.html        단어장/학생/결과 관리 화면
  quiz.html               학생용 퀴즈 화면 (로그인 불필요, 링크+코드로 접속)
  passage-analyzer.html   지문분석기 화면
  workbook.html            워크북 메이커 화면
  comprehension.html       O/X 리딩 워크북 화면
  design-tokens.css        나눔고딕 + 뉴트럴톤 색상·폰트 값 (홈페이지/화면 공용)
```

## 실행 전 환경변수

```
JWT_SECRET=<openssl rand -hex 32 로 생성한 랜덤 값>
FERNET_KEY=<python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
```
두 값 다 한 번 정하면 이후 계속 같은 값을 써야 해요. 바뀌면 기존 로그인 세션과
저장된 Gemini 키가 전부 무효가 됩니다.

## 로컬 실행

```bash
pip install -r requirements.txt
export JWT_SECRET=...
export FERNET_KEY=...
uvicorn app.main:app --reload --port 8000
```

## 인증 흐름

1. `POST /auth/signup` — 이름 + PIN + Gemini API 키로 선생님 계정 생성
2. `POST /auth/login` — 이름 + PIN으로 로그인, 세션 쿠키 발급 (httpOnly, secure, 30일)
3. 이후 `/api/*` 요청은 이 쿠키로 자동 인증됨 (로그인한 선생님 소속 데이터만 조회/수정)
4. 학생은 `/public/quiz/{access_code}/...` 경로로 로그인 없이 접속 (기존 방식 그대로)

## 화면 (홈페이지 / 4개 도구)

- `/` — 홈페이지. 로그인/회원가입 + 4개 도구 카드
- `/vocabulary/` — 단어장/학생/결과 관리 (선생님, 로그인 필요)
- `/quiz.html?code=학생코드` — 학생용 퀴즈 (로그인 불필요)
- `/passage-analyzer/`, `/workbook/`, `/comprehension/` — 각 도구 생성 화면 (로그인 필요)
- 전부 `static/design-tokens.css`의 나눔고딕 + 뉴트럴톤(회색 계열, 원색 없음) 적용

## PDF 다운로드

- 지문분석/워크북/OX 결과 모두 화면에서 "PDF 다운로드" 버튼으로 받을 수 있어요 (`/api/materials/{id}/pdf`)
- 나눔고딕 폰트(`app/assets/fonts/NanumGothic.ttf`, `NanumGothicBold.ttf`)를 프로젝트에 직접 번들해서 씀
  — 배포 서버가 구글 폰트 CDN에 접속을 못 해도 항상 정확히 나눔고딕으로 PDF가 나와요.

## 배포 (Render)

- `Dockerfile`, `render.yaml` 포함되어 있어요. Render에서 "New > Blueprint"로 이 레포를 연결하면
  `render.yaml`을 읽어서 자동으로 설정돼요.
- `JWT_SECRET`, `FERNET_KEY`는 Render가 배포 시 자동 생성해줘요 (render.yaml의 `generateValue: true`)
- **SQLite 파일이 재배포할 때마다 사라지지 않으려면 영구 디스크가 필요해요** — Render 무료 플랜은
  디스크를 지원하지 않아서 최소 Starter 플랜 이상이어야 해요. 계속 무료로 쓰고 싶으면 나중에
  Render Postgres(무료 티어)로 옮기는 걸 권장해요.
- **주의**: 이 개발 환경엔 Docker가 없어서 Dockerfile 자체를 빌드해서 테스트하지는 못했어요.
  문법과 구성은 표준적이라 문제 없을 거예요, 다만 Render에 처음 배포할 때 빌드 로그를 한 번 확인해주세요.

## 이번에 실제로 확인한 것

- 회원가입 → 로그인 상태 전환 (홈페이지, Playwright로 실제 렌더링 확인)
- 단어장 생성 → 단어 추가 → 학생 등록 (`/vocabulary/`)
- **학생이 로그인 없이 링크(`/quiz.html?code=학생코드`)로 접속 → 단어 퀴즈 응시 → 채점 → 결과 제출**
  까지 전체 흐름 실제 브라우저로 확인
- **PDF 다운로드**: 지문분석/워크북/OX 결과를 나눔고딕 번들 폰트로 실제 렌더링해서 이미지로 확인,
  실제 서버 통해 다운로드(`/api/materials/{id}/pdf`)까지 검증

## 아직 안 된 것 (다음에 이어서 할 것들)

- **워크북/OX 프롬프트 검수**: `prompts.py`의 워크북·OX 시스템 프롬프트는 이번 대화에서 정리된
  스펙을 바탕으로 새로 작성한 것이라, 실제로 돌려보고 결과 품질을 확인해야 해요.
- **Gemini 실제 호출 테스트**: 개발 환경 네트워크 제약으로 API 형식만 맞춰뒀고 실제 호출은
  못 해봤어요. (생성→저장→PDF 다운로드 파이프라인 자체는 가짜 응답으로 전체 흐름을 검증함)
- **Postgres 전환**: 선생님 수가 늘어나면 SQLite보다 Postgres를 권장해요
