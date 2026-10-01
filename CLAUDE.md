# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

- 이 프로젝트 참여자는 모두 한국인이기 때문에 md파일이나 주석은 모두 한국어로 작성해야 합니다.
- 참여한 개발자는 모두 초급 개발자이기 때문에 코드마다 주석을 달아서 쉽게 설명해주어야 합니다.
- 주석은 현재 작성된 코드에 달려있는 주석들을 참고하여, 기존 주석과 똑같은 방식과 형식으로 일관되게 작성하여야 합니다.

## 1. 프로젝트 개요
- **라이브러리 관리**: uv
- **라이브러리 사용**: fastapi, uvicorn[standard], httpx, pydantic[email], pydantic-settings, sqlalchemy, alembic, psycopg[binary], celery[redis], prometheus-client, grafana, pyjwt, cryptography, qdrant-client, python-multipart (개발용: ruff, pytest, pytest-asyncio, aiosqlite)
- **프로젝트 목적**: LLM이 VectorDB에 저장된 문서들의 내용을 답변에 반영하도록 만드는 RAG 시스템 구축
- **프로젝트 목표 기능**: VectorDB에 저장된 회사 문서를 참고하여 답변이 가능한 챗봇 기능, 회사 업무에 특화된 AI Agent를 생성하고 제어할 수 있는 기능 등
- **주요 특징**:
  - fastapi, uvicorn[standard]를 활용하여 웹 서버 구축
  - httpx를 활용하여 HTTP 요청 및 외부 API 호출
  - pydantic과 pydantic-settings로 데이터 검증 및 환경 변수 관리 지원
  - Supabase에서 제공하는 무료티어 PostgreSQL DB를 사용
  - ORM은 SQLAlchemy을 사용하며, 통신은 psycopg[binary]를 활용 
  - DB 스키마 버전 관리 및 마이그레이션은 alembic으로 관리
  - Qdrant에서 제공하는 무료티어 Vector DB를 사용 (개발 단계. 납품 시 고객사 자체 Qdrant로 교체 가능)
  - qdrant-client를 통해 Vector DB와 데이터를 주고 받음
  - 임베딩 모델(BGE-M3 예정)과 LLM(Qwen, GPT-OSS 등)은 앱 안에서 직접 실행하지 않고, OpenAI 호환 HTTP API(`/v1/embeddings`, `/v1/chat/completions`)로 httpx를 통해 호출
    - 개발: 로컬 Ollama / 납품: 고객사 GPU 서버(vLLM, TEI 등)
  - **배포 목표**: Docker 컨테이너로 만들어 폐쇄망(인터넷 차단) 기업 환경에 납품할 수 있어야 함

## 2. 백엔드 개발 및 빌드 명령어 (Commands)
백엔드 개발 시에는 `backend/` 디렉토리에서 진행합니다. (uv 프로젝트 루트)
- **의존성 설치**: `uv sync`
- **패키지 추가**: `uv add <패키지명>` (개발 도구는 `uv add --dev <패키지명>`)
- **개발용 임베딩 서버 실행** (서버 실행 전 필수): `_deploy/` 디렉토리에서 `docker compose up -d embedding` (Ollama + bge-m3, CPU 전용, 포트 8081)
- **서버 실행**: `uv run uvicorn src.main:app --reload`
- **마이그레이션 생성**: `uv run alembic revision --autogenerate -m "변경 내용"`
- **마이그레이션 적용**: `uv run alembic upgrade head`
- **린트 검사**: `uv run ruff check .`
- **테스트 실행**: `uv run pytest` (테스트 코드는 `backend/tests/`, 실제 DB 대신 메모리 SQLite 사용)
- **챗봇 답변 품질 평가**: `uv run python -m scripts.evaluate_chat` (실제 검색 + LLM으로 `scripts/chat_eval_set.json`의 질문에 답변을 만들어 정답 값 포함, 지어내기 방지, 출처 표시, 한자 섞임, 응답 시간을 출력. 프롬프트(`src/services/rag/chat/prompt.py`)·모델을 바꾼 뒤 비교용)
- **개발용 LLM**: 맥북에 설치한 Ollama 앱(GPU, 포트 11434)에 `ollama pull qwen3.5:9b`로 받은 모델 사용 (`.env`의 `LLM_BASE_URL=http://localhost:11434/v1`)
- **검색 품질 평가**: `uv run python -m scripts.evaluate_search` (실제 Qdrant + 임베딩 서버로 `scripts/search_eval_set.json`의 질문을 검색해 Hit@1, Recall@5, MRR 등을 출력. 청크 크기·임베딩 모델 등을 바꾼 뒤 품질 비교용)

### 프론트엔드 (기능 테스트용 화면)
프론트엔드 개발 시에는 `frontend/` 디렉토리에서 진행합니다. (React + TypeScript + Vite, 아이콘 lucide-react, 폰트 pretendard)
- **의존성 설치**: `npm install`
- **개발 서버 실행**: `npm run dev` → http://localhost:3000 (백엔드 서버가 먼저 켜져 있어야 함)
- **타입 검사 + 빌드**: `npm run build` (결과물: `frontend/dist/`)
- **API 호출**: 모든 요청은 `/api`로 시작하고, 개발 서버가 백엔드(http://localhost:8000)로 대신 전달(프록시)함 (`vite.config.ts` 참고)
- **메뉴 추가**: `src/constants/menu.ts`에 메뉴를 정의하고, 기능을 완성하면 `ready: true`로 바꾼 뒤 `src/App.tsx`에 화면을 연결
- **폐쇄망 대비**: 폰트, 아이콘 등 외부 CDN을 사용하지 않고 npm 패키지로 설치하여 빌드 결과에 포함시킴

## 3. 주의
- **모델 추가**: 새 SQLAlchemy 모델은 `src/core/base.py`의 `Base`를 상속하고, `src/migrations/env.py`에 모델 모듈 import를 추가해야 alembic이 인식함
- **API 권한**: 로그인이 필요한 API는 `src/services/iam/auth/dependencies.py`의 `CurrentUser`(로그인 사용자), `AdminUser`(관리자) 또는 `require_roles(...)`를 라우터 매개변수로 사용함. 의존 방향은 `auth -> user` 한 방향만 허용 (user의 service/repository에서 auth를 import 금지)
- **환경 변수 추가**: `src/core/config.py`에 필드를 추가하고 `backend/.env.example`에도 항목을 추가해야 함
- **설정**: `backend/src/core/config.py`가 `.env`의 모든 환경변수를 로드하도록 해야 함

## 4. 규칙
- **환경 변수 관리**: 데이터베이스 URL이나 AWS 관련 비밀키는 절대 코드에 하드코딩하지 말고, `src/core/config.py`를 통해 `.env`에서 안전하게 로드하여 사용해야 합니다.
- **린트**: `pyproject.toml`의 `[tool.ruff]` 설정에 따라 `line-length = 100`, `select = ["E", "F", "I", "UP", "B"]` (pycodestyle, pyflakes, isort)를 준수합니다. 백엔드 작업을 마치기 전 `uv run ruff check .`를 실행하세요.
- **테스트**: 기능을 추가하거나 수정하면 `backend/tests/` 아래에 해당 기능의 테스트도 함께 추가·수정해야 합니다. 테스트 파일 위치는 `src/services/` 구조를 따릅니다 (예: `src/services/iam/auth` -> `tests/iam/test_auth.py`). 백엔드 작업을 마치기 전 `uv run pytest`를 실행하여 전체 테스트가 통과하는지 확인하세요. 테스트는 실제 DB(Supabase)에 연결하지 않고 `tests/conftest.py`의 fixture(메모리 SQLite)를 사용해야 합니다.

- **외부 시스템 연동 (폐쇄망 납품 대비)**:
  - 모든 외부 연결 정보(주소, API 키, 모델 이름, 벡터 차원 등)는 코드에 적지 말고 `src/core/config.py`의 환경 변수로 받아야 합니다. 환경 변수만 바꾸면 클라우드/고객사 환경을 전환할 수 있어야 합니다.
  - Vector DB, 임베딩, LLM을 호출하는 코드는 각각 `src/core/` 아래 한 파일에만 둡니다. 다른 제품으로 교체할 때 그 파일만 수정하면 되도록 하기 위함입니다.
  - 앱이 실행 중에 인터넷(모델 자동 다운로드, 외부 CDN 등)에 의존하지 않도록 해야 합니다.

## 5. 주석
- **코드 수정**: 클로드가 코드를 수정한 경우 `[수정]` 표시를 꼭 표기하고 `기존`과 `변경` 후가 어떻게 다른지 각각 설명해 주어야 한다.
- **수정 확인 후**: 개발자가 클로드의 수정 내용을 모두 확인한 경우, `[수정]` 표시를 지우고 `*` 표시를 하여 수정된 내용을 확인했음을 표시한다.

