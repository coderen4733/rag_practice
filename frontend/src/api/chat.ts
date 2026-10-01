// 챗봇(chat) API 호출 함수
//  - 백엔드 POST /chat/stream (스트리밍 답변), GET /chat/status (LLM 연결 상태)
//  - 대화방(대화 이력) API : 목록 / 열기 / 제목 변경 / 삭제
//
// 📌 스트리밍(SSE) 응답 읽는 방법
//  - 백엔드는 답변을 아래처럼 "이벤트" 단위로 조금씩 보냄 (이벤트 사이는 빈 줄)
//      event: sources\ndata: [...]\n\n         <- 근거 문서 목록
//      event: token\ndata: {"text": "연차"}\n\n  <- 답변 조각 (여러 번)
//      event: done\ndata: {...}\n\n             <- 끝 (장애 시 event: error)
//  - 도착한 글자를 buffer에 모았다가, 빈 줄("\n\n")이 나오면 이벤트 하나로 잘라서 처리

import { request, requestStream, unwrap } from "./client";
// 대화방 관련 타입 import
import type {
  ApiResponse,
  ChatDoneInfo,
  ChatRequest,
  ChatSource,
  ChatStatus,
  Conversation,
  ConversationDeleteResult,
  ConversationDetail,
  PageResult,
} from "./types";

// 스트리밍 중에 이벤트가 올 때마다 호출할 함수들 (화면에서 넘겨줌)
export interface ChatStreamHandlers {
  onSources: (sources: ChatSource[]) => void; // 근거 문서 목록 도착
  onToken: (text: string) => void; // 답변 조각 도착
  // 답변 끝 정보에 대화방 id, 제목, 검색에 사용한 질문 (기존: model, elapsed_ms)
  onDone: (info: ChatDoneInfo) => void; // 답변 끝
  onError: (message: string) => void; // 답변 도중 장애
}

// 챗봇 답변 스트리밍 (POST /chat/stream) - 로그인한 사용자 누구나
//  - signal: "중지" 버튼으로 요청을 취소할 때 사용
//  - 스트리밍 시작 전 에러(401, 503 등)는 ApiError로 던짐
export async function streamChat(
  input: ChatRequest,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await requestStream("/chat/stream", input, signal);
  if (!response.body) throw new Error("스트리밍 응답을 읽을 수 없습니다.");

  // getReader(): 응답 본문을 조금씩 읽는 도구 / TextDecoder: 바이트 -> 글자 변환
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false; // done 또는 error 이벤트를 받았는지

  while (true) {
    const { value, done } = await reader.read();
    if (done) break; // 서버가 응답을 끝까지 보냄
    // stream: true => 한글처럼 여러 바이트로 된 글자가 중간에 잘려 와도 올바르게 이어 붙임
    buffer += decoder.decode(value, { stream: true });

    // 빈 줄(\n\n)이 나올 때마다 이벤트 하나씩 처리
    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex !== -1) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      finished = dispatchEvent(block, handlers) || finished;
      separatorIndex = buffer.indexOf("\n\n");
    }
  }

  // done/error 없이 끝났다면 네트워크가 중간에 끊긴 것
  if (!finished) handlers.onError("답변이 중간에 끊겼습니다. 다시 시도해 주세요.");
}

// 이벤트 하나 처리 => 끝을 알리는 이벤트(done, error)면 true
function dispatchEvent(block: string, handlers: ChatStreamHandlers): boolean {
  let eventName = "";
  let dataText = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) eventName = line.slice("event:".length).trim();
    if (line.startsWith("data:")) dataText += line.slice("data:".length).trim();
  }
  if (!eventName || !dataText) return false;

  const data = JSON.parse(dataText);
  switch (eventName) {
    case "sources":
      handlers.onSources(data as ChatSource[]);
      return false;
    case "token":
      handlers.onToken((data as { text: string }).text);
      return false;
    case "done":
      handlers.onDone(data as ChatDoneInfo);
      return true;
    case "error":
      handlers.onError((data as { message: string }).message);
      return true;
    default:
      return false; // 모르는 이벤트는 무시
  }
}

// LLM 연결 상태 (GET /chat/status) - 로그인한 사용자 누구나
export async function getChatStatus(): Promise<ChatStatus> {
  return unwrap(await request<ApiResponse<ChatStatus>>("/chat/status"));
}

// ───────────── 대화방(대화 이력) API ─────────────
//  - 모두 "내 대화방"만 다룰 수 있음 (다른 사람의 대화방은 404)

// 내 대화방 목록 (GET /chat/conversations) - 최근에 대화한 순서
export async function listConversations(page = 1, size = 50): Promise<PageResult<Conversation>> {
  return unwrap(
    await request<ApiResponse<PageResult<Conversation>>>("/chat/conversations", {
      query: { page, size },
    }),
  );
}

// 대화방 열기 (GET /chat/conversations/{id}) - 대화방 정보 + 메시지 전체
export async function getConversation(conversationId: number): Promise<ConversationDetail> {
  return unwrap(
    await request<ApiResponse<ConversationDetail>>(`/chat/conversations/${conversationId}`),
  );
}

// 대화방 제목 변경 (PATCH /chat/conversations/{id})
export async function renameConversation(conversationId: number, title: string): Promise<Conversation> {
  return unwrap(
    await request<ApiResponse<Conversation>>(`/chat/conversations/${conversationId}`, {
      method: "PATCH",
      body: { title },
    }),
  );
}

// 대화방 삭제 (DELETE /chat/conversations/{id}) - 대화방 안의 메시지도 함께 삭제
export async function deleteConversation(conversationId: number): Promise<ConversationDeleteResult> {
  return unwrap(
    await request<ApiResponse<ConversationDeleteResult>>(`/chat/conversations/${conversationId}`, {
      method: "DELETE",
    }),
  );
}
