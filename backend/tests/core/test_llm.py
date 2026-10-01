#  * LLM 서버 호출 코드(src/core/llm.py) 테스트
#  - 요청 형식(생각 모드 끄기 포함), 한 번에 받기, 스트리밍 해석, 연결 확인, 에러 상황 확인
#  - 실제 LLM 서버 대신 httpx.MockTransport(가짜 서버)를 사용 (test_embedding.py와 같은 방식)

import json

import httpx
import pytest

from src.core import llm
from src.core.config import get_settings

settings = get_settings()

MESSAGES = [{"role": "user", "content": "안녕?"}]


# 스트리밍 응답 본문 만들기 (OpenAI 호환 SSE 형식)
#  - pieces 안의 dict가 각 줄의 delta가 됨, 마지막에 data: [DONE]
def sse_body(deltas: list[dict]) -> bytes:
    lines = [
        f"data: {json.dumps({'choices': [{'index': 0, 'delta': delta}]}, ensure_ascii=False)}\n\n"
        for delta in deltas
    ]
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


# 가짜 LLM 서버를 만들어서 llm 파일에 끼워 넣는 fixture
#  - handler: 요청을 받아 응답을 돌려주는 함수
#  - 반환값: 가짜 서버가 받은 요청 목록 (url, payload) - 확인용
@pytest.fixture
def fake_llm_server(monkeypatch):
    def _create(handler):
        requests = []

        def recording_handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content) if request.content else None
            requests.append({"url": str(request.url), "method": request.method, "payload": payload})
            return handler(request)

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(recording_handler), base_url=settings.llm_base_url
        )
        monkeypatch.setattr(llm, "_http_client", client)
        return requests

    return _create


# 정상 응답 (한 번에 받기)
def ok_handler(request):
    return httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": "안녕하세요"}}]}
    )


# ─────────────────────────────────────────────
# 1. 한 번에 받기 (chat_completion)
# ─────────────────────────────────────────────
# 정상 요청 => OpenAI 호환 형식으로 요청하고 답변을 돌려받음 (생각 모드 끄기 값 포함)
async def test_chat_completion_success(fake_llm_server):
    requests = fake_llm_server(ok_handler)

    answer = await llm.chat_completion(MESSAGES)

    assert answer == "안녕하세요"
    request = requests[0]
    assert request["url"] == "http://llm.test/v1/chat/completions"
    payload = request["payload"]
    assert payload["model"] == "test-model"
    assert payload["messages"] == MESSAGES
    assert payload["stream"] is False
    assert payload["reasoning_effort"] == "none"  # 생각 모드 끄기
    assert payload["temperature"] == settings.llm_temperature
    assert payload["max_tokens"] == settings.llm_max_tokens


# LLM_REASONING_EFFORT를 비우면 => reasoning_effort를 보내지 않음
async def test_chat_completion_without_reasoning_effort(fake_llm_server, monkeypatch):
    requests = fake_llm_server(ok_handler)
    monkeypatch.setattr(llm.settings, "llm_reasoning_effort", None)

    await llm.chat_completion(MESSAGES)

    assert "reasoning_effort" not in requests[0]["payload"]


# LLM_EXTRA_BODY => 요청 본문에 그대로 합쳐짐 (예: vLLM의 생각 모드 끄기 옵션)
async def test_chat_completion_extra_body(fake_llm_server, monkeypatch):
    requests = fake_llm_server(ok_handler)
    extra = {"chat_template_kwargs": {"enable_thinking": False}}
    monkeypatch.setattr(llm.settings, "llm_extra_body", extra)

    await llm.chat_completion(MESSAGES)

    assert requests[0]["payload"]["chat_template_kwargs"] == {"enable_thinking": False}


# 서버 에러 응답(예: 없는 모델 => 404) => LLMError
async def test_chat_completion_server_error(fake_llm_server):
    fake_llm_server(lambda request: httpx.Response(404, json={"error": "model not found"}))

    with pytest.raises(llm.LLMError, match="404"):
        await llm.chat_completion(MESSAGES)


# 연결 실패(예: Ollama가 꺼져 있음) => LLMError
async def test_chat_completion_connection_error(fake_llm_server):
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    fake_llm_server(handler)

    with pytest.raises(llm.LLMError, match="연결할 수 없습니다"):
        await llm.chat_completion(MESSAGES)


# 응답 형식이 이상함 => LLMError
async def test_chat_completion_invalid_response(fake_llm_server):
    fake_llm_server(lambda request: httpx.Response(200, json={"message": "hello"}))

    with pytest.raises(llm.LLMError, match="형식"):
        await llm.chat_completion(MESSAGES)


# init_llm() 전에 사용하면 => LLMError
async def test_chat_completion_before_init(monkeypatch):
    monkeypatch.setattr(llm, "_http_client", None)

    with pytest.raises(llm.LLMError):
        await llm.chat_completion(MESSAGES)


# ─────────────────────────────────────────────
# 2. 스트리밍 (stream_chat_completion)
# ─────────────────────────────────────────────
# 답변 조각을 차례대로 받음 (생각 모드 내용, 빈 조각은 건너뜀, [DONE]에서 끝)
async def test_stream_chat_completion(fake_llm_server):
    body = sse_body(
        [
            {"role": "assistant", "content": ""},  # 첫 줄: 내용 없음 => 건너뜀
            {"reasoning": "생각 중..."},  # 생각 모드 내용 => 화면에 보여주지 않음
            {"content": "연차는"},
            {"content": " 3근무일 전"},
        ]
    )
    requests = fake_llm_server(
        lambda request: httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )
    )

    pieces = [piece async for piece in llm.stream_chat_completion(MESSAGES)]

    assert pieces == ["연차는", " 3근무일 전"]
    assert requests[0]["payload"]["stream"] is True


# 스트리밍 요청에 서버가 에러를 응답 => LLMError
async def test_stream_chat_completion_server_error(fake_llm_server):
    fake_llm_server(lambda request: httpx.Response(500, text="internal error"))

    with pytest.raises(llm.LLMError, match="500"):
        async for _ in llm.stream_chat_completion(MESSAGES):
            pass


# 스트리밍 응답 형식이 이상함 => LLMError
async def test_stream_chat_completion_invalid_line(fake_llm_server):
    fake_llm_server(lambda request: httpx.Response(200, content=b"data: {not json}\n\n"))

    with pytest.raises(llm.LLMError, match="형식"):
        async for _ in llm.stream_chat_completion(MESSAGES):
            pass


# ─────────────────────────────────────────────
# 3. 연결 확인 (check_llm_connection)
# ─────────────────────────────────────────────
# 모델 목록에 설정한 모델이 있으면 => 통과
async def test_check_llm_connection_ok(fake_llm_server):
    requests = fake_llm_server(
        lambda request: httpx.Response(200, json={"data": [{"id": "test-model"}, {"id": "other"}]})
    )

    await llm.check_llm_connection()

    assert requests[0]["url"] == "http://llm.test/v1/models"
    assert requests[0]["method"] == "GET"


# 모델 목록에 설정한 모델이 없으면 => LLMError (사용 가능한 모델 이름을 알려줌)
async def test_check_llm_connection_model_missing(fake_llm_server):
    fake_llm_server(lambda request: httpx.Response(200, json={"data": [{"id": "other-model"}]}))

    with pytest.raises(llm.LLMError, match="other-model"):
        await llm.check_llm_connection()


# 연결 실패 => LLMError
async def test_check_llm_connection_down(fake_llm_server):
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    fake_llm_server(handler)

    with pytest.raises(llm.LLMError, match="연결할 수 없습니다"):
        await llm.check_llm_connection()
