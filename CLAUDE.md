# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

- 이 프로젝트 참여자는 모두 한국인이기 때문에 md파일이나 주석은 모두 한국어로 작성해야 합니다.
- 참여한 개발자는 모두 초급 개발자이기 때문에 코드마다 주석을 달아서 쉽게 설명해주어야 합니다.
- 주석은 현재 작성된 코드에 달려있는 주석들을 참고하여, 기존 주석과 똑같은 방식과 형식으로 일관되게 작성하여야 합니다.

## 1. 프로젝트 개요
- **라이브러리 관리**: uv
- **라이브러리 사용**: fastapi, uvicorn[standard], httpx, pydantic, pydantic-settings, sqlalchemy, alembic, psycopg[binary], celery[redis], prometheus-client, grafana, python-jose[cryptography], qdrant-client, fastembed
- **프로젝트 목적**: LLM이 VectorDB에 저장된 문서들의 내용을 답변에 반영하도록 만드는 RAG 시스템 구축
- **프로젝트 목표 기능**: VectorDB에 저장된 회사 문서를 참고하여 답변이 가능한 챗봇 기능, 회사 업무에 특화된 AI Agent를 생성하고 제어할 수 있는 기능 등
- **주요 특징**:
  - fastapi, uvicorn[standard]를 활용하여 웹 서버 구축
  - httpx를 활용하여 HTTP 요청 및 외부 API 호출
  - pydantic과 pydantic-settings로 데이터 검증 및 환경 변수 관리 지원
  - Supabase에서 제공하는 무료티어 PostgreSQL DB를 사용
  - ORM은 SQLAlchemy을 사용하며, 통신은 psycopg[binary]를 활용 
  - DB 스키마 버전 관리 및 마이그레이션은 alembic으로 관리
  - Qdrant에서 제공하는 무료티어 Vector DB를 사용
  - qdrant-client를 통해 Vector DB와 데이터를 주고 받음
  - 데이터는 fastembed를 통해 벡터화 (모델은 BGE-M3 사용 예정)

## 2. 백엔드 개발 및 빌드 명령어 (Commands)
백엔드 개발 시에는 `backend/` 디렉토리에서 진행합니다. (uv 프로젝트 루트)
- **의존성 설치**: `uv sync`
- **패키지 추가**: `uv add <패키지명>`
- **린트 검사**: `uv run ruff check .`

## 3. 주의
- **설정**: `backend/core/config.py`가 `.env`의 모든 환경변수를 로드하도록 해야 함

## 4. 규칙
- **환경 변수 관리**: 데이터베이스 URL이나 AWS 관련 비밀키는 절대 코드에 하드코딩하지 말고, `core/config.py`를 통해 `.env`에서 안전하게 로드하여 사용해야 합니다.
- **린트**: `pyproject.toml`의 `[tool.ruff]` 설정에 따라 `line-length = 100`, `select = ["E", "F", "I", "UP", "B"]` (pycodestyle, pyflakes, isort)를 준수합니다. 백엔드 작업을 마치기 전 `uv run ruff check .`를 실행하세요.