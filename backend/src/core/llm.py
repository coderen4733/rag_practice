#  * LLM(답변 생성 AI) 서버 호출 담당
#  - 질문과 참고 문서를 LLM 서버에 보내서 답변을 받아오는 기능
#    => CLAUDE.md 규칙: LLM을 호출하는 코드는 이 파일 한 곳에만 둠
#       (다른 LLM 서버로 바꿀 때 이 파일과 .env만 수정하면 됨)
#
# 📌 OpenAI 호환 API (POST /v1/chat/completions)
#  - Ollama, vLLM 등 대부분의 LLM 서버가 지원하는 표준 형식
#  - 요청: {"model": "qwen3.5:9b", "messages": [{"role": "system", "content": "..."},
#                                                {"role": "user", "content": "..."}]}
#    - role "system": AI에게 주는 규칙 (예: "문서 내용만 근거로 답하라")
#    - role "user"  : 사용자의 질문
#    - role "assistant": AI의 이전 답변 (대화를 이어갈 때 사용)
#
# 📌 두 가지 답변 방식
#  - chat_completion       : 답변이 "다 만들어진 뒤" 한 번에 받음
#  - stream_chat_completion: 답변이 만들어지는 "대로" 조금씩 받음 (스트리밍)
#    => 화면에 글자가 바로바로 나타나서, 사용자가 기다리는 느낌이 훨씬 적음

import json
from collections.abc import AsyncIterator

import httpx

from src.core.config import get_settings

# get_settings()를 호출하여 환경변수 객체 가져오기
settings = get_settings()

# 서버 전체에서 함께 쓰는 HTTP 클라이언트 (init_llm()이 호출되기 전까지는 None)
_http_client: httpx.AsyncClient | None = None


# LLM 관련 에러 (서버 연결 실패, 응답 형식 이상, 모델 없음 등)
class LLMError(Exception):
    pass


# LLM 서버용 HTTP 클라이언트 생성 - src/main.py의 lifespan에서 사용
def init_llm() -> None:
    global _http_client
    # API 키가 설정된 경우에만 인증 헤더 (Ollama처럼 키가 필요 없는 서버는 생략)
    headers = {}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    _http_client = httpx.AsyncClient(
        # base_url: 요청 주소의 앞부분 => post("/chat/completions")는 {base_url}/chat/completions
        base_url=settings.llm_base_url,
        headers=headers,
        timeout=settings.llm_timeout,
    )


# 서버 전체에서 함께 쓰는 HTTP 클라이언트 꺼내기
def _get_http_client() -> httpx.AsyncClient:
    if _http_client is None:
        raise LLMError("LLM 클라이언트가 아직 만들어지지 않았습니다.")
    return _http_client


# LLM 서버에 보낼 요청 본문 만들기 (이 파일 안에서만 사용)
#  - messages: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
#  - stream: True면 스트리밍 방식으로 요청
def _build_payload(messages: list[dict[str, str]], stream: bool) -> dict:
    payload: dict = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "stream": stream,
    }
    # 생각 모드 조절 (값이 있을 때만 보냄)
    #  - Ollama에서 Qwen3.5의 생각 모드를 끄려면 "none" (끄지 않으면 답변이 매우 느려짐)
    if settings.llm_reasoning_effort:
        payload["reasoning_effort"] = settings.llm_reasoning_effort
    # LLM 서버 종류별 추가 옵션 (예: vLLM의 chat_template_kwargs)
    #  - update: 딕셔너리에 다른 딕셔너리의 값을 덮어써서 합침
    payload.update(settings.llm_extra_body)
    return payload


# HTTP 에러 => 사람이 읽을 수 있는 LLMError (이 파일 안에서만 사용)
def _to_llm_error(err: httpx.HTTPError, status_code: int | None = None) -> LLMError:
    if status_code is not None:
        # 서버는 켜져 있지만 에러를 응답한 경우 (예: 모델 이름이 틀림 => 404)
        return LLMError(f"LLM 서버가 에러를 응답했습니다. (상태 코드: {status_code})")
    # 서버에 연결 자체가 안 되는 경우 (예: Ollama가 꺼져 있음, 시간 초과)
    return LLMError(f"LLM 서버에 연결할 수 없습니다. ({err!r})")


# 답변을 한 번에 받기
#  - 사용법: answer = await chat_completion([{"role": "user", "content": "안녕?"}])
async def chat_completion(messages: list[dict[str, str]]) -> str:
    client = _get_http_client()
    # 1. LLM 서버에 요청
    try:
        response = await client.post("/chat/completions", json=_build_payload(messages, False))
        response.raise_for_status()
    except httpx.HTTPStatusError as err:
        raise _to_llm_error(err, err.response.status_code) from err
    except httpx.HTTPError as err:
        raise _to_llm_error(err) from err

    # 2. 응답에서 답변 꺼내기
    #  - 응답: {"choices": [{"message": {"role": "assistant", "content": "답변"}}]}
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as err:
        raise LLMError("LLM 서버의 응답 형식이 올바르지 않습니다.") from err
    return content or ""


# 답변을 만들어지는 대로 조금씩 받기 (스트리밍)
#  - 사용법:
#      async for piece in stream_chat_completion(messages):
#          print(piece, end="")   # "안", "녕", "하세요" ... 처럼 조각이 차례로 들어옴
#  - AsyncIterator: "async for"로 하나씩 꺼낼 수 있는 값의 흐름
#  - 함수 안의 yield: 값을 하나 내보내고, 다음 값을 요청받을 때까지 잠시 멈춤
async def stream_chat_completion(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    client = _get_http_client()
    try:
        # client.stream(): 응답을 한 번에 받지 않고 도착하는 대로 조금씩 읽음
        async with client.stream(
            "POST", "/chat/completions", json=_build_payload(messages, True)
        ) as response:
            if response.status_code >= 400:
                await response.aread()  # 에러 응답 본문을 끝까지 읽고 연결 정리
                raise LLMError(
                    f"LLM 서버가 에러를 응답했습니다. (상태 코드: {response.status_code})"
                )
            # 스트리밍 응답은 한 줄씩 도착함 (SSE 형식)
            #   data: {"choices": [{"delta": {"content": "안"}}]}
            #   data: {"choices": [{"delta": {"content": "녕"}}]}
            #   data: [DONE]          <- 답변 끝
            async for line in response.aiter_lines():
                piece = _parse_stream_line(line)
                if piece is None:  # 답변 끝 신호
                    return
                if piece:  # 빈 조각(생각 모드 내용 등)은 건너뜀
                    yield piece
    except httpx.HTTPError as err:
        raise _to_llm_error(err) from err


# 스트리밍 응답 한 줄 해석하기 (이 파일 안에서만 사용)
#  - 반환값: 답변 조각(str), 내용 없음(""), 답변 끝(None)
def _parse_stream_line(line: str) -> str | None:
    line = line.strip()
    # "data: "로 시작하지 않는 줄(빈 줄 등)은 무시
    if not line.startswith("data:"):
        return ""
    data = line[len("data:") :].strip()
    if data == "[DONE]":
        return None
    try:
        delta = json.loads(data)["choices"][0].get("delta", {})
    except (KeyError, IndexError, TypeError, ValueError) as err:
        raise LLMError("LLM 서버의 스트리밍 응답 형식이 올바르지 않습니다.") from err
    # delta.content: 답변 조각 / delta.reasoning: 생각 모드 내용 (화면에 보여주지 않음)
    return delta.get("content") or ""


# LLM 서버 연결 확인 - src/main.py의 lifespan, 시스템 상태 API에서 사용
#  - 모델 목록(GET /v1/models)을 받아서, 설정한 모델(LLM_MODEL)이 있는지 확인
#  - 답변을 실제로 생성해 보지 않는 이유: 모델을 GPU에 올리는 데 시간이 걸릴 수 있어서
#    (서버 시작이 느려지지 않도록 가벼운 확인만 함)
async def check_llm_connection() -> None:
    client = _get_http_client()
    try:
        response = await client.get("/models")
        response.raise_for_status()
        model_ids = [model["id"] for model in response.json()["data"]]
    except httpx.HTTPStatusError as err:
        raise _to_llm_error(err, err.response.status_code) from err
    except httpx.HTTPError as err:
        raise _to_llm_error(err) from err
    except (KeyError, TypeError, ValueError) as err:
        raise LLMError("LLM 서버의 모델 목록 형식이 올바르지 않습니다.") from err
    if settings.llm_model not in model_ids:
        raise LLMError(
            f"LLM 서버에 '{settings.llm_model}' 모델이 없습니다. "
            f"(사용 가능한 모델: {', '.join(model_ids) or '없음'})"
        )


# LLM HTTP 클라이언트 종료 함수 - src/main.py의 lifespan에서 사용
async def close_llm() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
