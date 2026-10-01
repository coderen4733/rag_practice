// 챗봇 화면
//  - 등록된 문서를 근거로 AI가 답변하는 대화 화면 (POST /chat/stream)
//    - 답변은 만들어지는 대로 글자가 바로바로 표시됨 (스트리밍)
//    - 답변 진행 단계(검색 -> 문서 읽기 -> 답변 작성)와 걸린 시간을 실시간으로 표시하고,
//      답변 글자를 타자 치듯 하나씩 보여줌 (components/chat/ChatProgress.tsx 참고)
//    - 답변 위에 근거 문서 카드를 보여주고, 답변 안의 [1] 번호를 누르면 해당 근거를 펼침
//      (기존: 답변 아래에 근거 문서 목록)
//    - 답변 생성 중 "중지" 버튼으로 취소 가능
//  - 대화 이어가기 + 대화 이력
//    - 같은 대화방에서는 이전 대화를 참고해서 이어서 답함 (질문/답변은 서버에 저장됨)
//      - 왼쪽 대화 목록에서 예전 대화를 다시 열거나, "새 대화"로 새로 시작
//      - 주소에 대화방 번호가 붙음 (예: /chat?conversation=3) => 새로고침해도 그 대화가 열림
//      - "중지"했거나 에러가 난 질문은 저장되지 않음 (완성된 질문/답변만 저장)

import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
// 삭제 확인 창의 휴지통 아이콘(Trash2)
import { MessagesSquare, Send, Square, Trash2 } from "lucide-react";
// 주소의 ?conversation=3 값을 읽고 바꾸기 위한 useSearchParams
import { useSearchParams } from "react-router-dom";

// 대화방 API 함수 (목록, 열기, 제목 변경, 삭제)
import {
  deleteConversation,
  getChatStatus,
  getConversation,
  listConversations,
  renameConversation,
  streamChat,
} from "../api/chat";
import { ApiError } from "../api/client";
import type { ChatSource, ChatStatus, Conversation, ConversationMessage } from "../api/types";
// AnswerText 대신 진행 단계 표시 + 타자 효과 답변 부품 사용
//  - import { AnswerText } from "../components/chat/AnswerText";
import {
  ChatProgressSteps,
  ChatProgressSummary,
  StreamingAnswer,
  type ChatProgressTimes,
} from "../components/chat/ChatProgress";
// 근거 문서 카드 부품 (답변 위에 표시, 읽는 중인 문서 표시, 읽기 속도 보정)
import { recordReadingSpeed, SourceCards, toSourceCardItems } from "../components/chat/SourceCards";
// 대화방 목록 부품 (화면 왼쪽)
import { ConversationList } from "../components/chat/ConversationList";
import { Badge } from "../components/ui/Badge";
// 불러오는 중 표시(Spinner), 삭제 확인 창(Modal)
import { Alert, Spinner } from "../components/ui/Feedback";
import { Modal } from "../components/ui/Modal";
import { useAuth } from "../contexts/AuthContext";
import { displayName } from "../utils/format";

// 예시 질문 (md 폴더의 테스트 문서 내용과 관련된 질문들)
const SAMPLE_QUESTIONS = [
  "부모님이 돌아가시면 휴가는 며칠이고 경조금은 얼마인가요?",
  "법에서 정한 연차와 우리 회사 연차는 며칠씩이야?",
  "직원을 해고하려면 며칠 전에 미리 알려줘야 하나요?",
  "2031년 매출 목표는 얼마야?",
];

// 대화 메시지 1개
interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  sources?: ChatSource[]; // 근거 문서 (AI 답변만)
  status?: "streaming" | "done" | "error" | "stopped"; // AI 답변 상태
  error?: string;
  model?: string;
  // elapsedMs(전체 걸린 시간) 대신 단계별 시각 기록(progress)
  //  - 검색 끝 / 첫 글자 도착 / 답변 끝 시각을 화면에서 직접 기록 => 단계별 시간 표시
  progress?: ChatProgressTimes;
  // 검색에 사용한 질문 (AI 답변만)
  //  - 이어서 묻는 질문을 LLM이 다시 써서 검색한 경우에만 값이 있음 (질문과 같으면 비워둠)
  //    예) 질문 "그럼 신입사원은?" => 검색 "신입사원의 연차는 며칠인가?"
  searchQuery?: string;
}

// 에러 => 화면에 보여줄 문구 (DocumentsPage와 같은 방식)
const errorMessage = (error: unknown) =>
  error instanceof ApiError ? error.message : "알 수 없는 오류가 발생했습니다.";

// 서버에 저장된 메시지 => 화면용 메시지로 변환 (예전 대화를 다시 열 때 사용)
//  - nextId: 화면용 메시지 번호를 하나씩 발급하는 함수
//  - 답변 메시지에는 바로 앞 질문의 "검색에 사용한 질문"을 붙여줌 (질문과 다를 때만)
function toChatMessages(items: ConversationMessage[], nextId: () => number): ChatMessage[] {
  let lastQuestion = "";
  let lastSearchQuery: string | null = null;
  return items.map((item) => {
    if (item.role === "user") {
      lastQuestion = item.content;
      lastSearchQuery = item.search_query;
      return { id: nextId(), role: "user", text: item.content };
    }
    return {
      id: nextId(),
      role: "assistant",
      text: item.content,
      sources: item.sources ?? [],
      status: "done",
      model: item.model ?? undefined,
      searchQuery: lastSearchQuery && lastSearchQuery !== lastQuestion ? lastSearchQuery : undefined,
    };
  });
}

// AI 답변 1개 + 근거 문서 목록
// 근거 문서를 답변 "위"에 카드로 보여주도록 (components/chat/SourceCards.tsx)
//  - 근거 문서가 도착하면 바로 답변 위에 카드로 표시
//    (유사도 캡슐, "자세히 보기"로 원문 펼치기, 읽는 중인 문서는 빨간 테두리)
function AssistantMessage({ message }: { message: ChatMessage }) {
  // 답변의 [n]을 눌렀을 때 펼칠 근거 카드 정보
  //  - focus 하나로 관리 (펼치기, 강조, 스크롤은 SourceCards가 처리)
  //    at: 누른 시각 - 같은 번호를 다시 눌러도 "새로 누름"으로 알아차리게 하기 위함
  const [focus, setFocus] = useState<{ number: number; at: number } | null>(null);
  const showSource = (number: number) => setFocus({ number, at: Date.now() });

  const sources = toSourceCardItems(message.sources ?? []);
  // 첫 답변 글자를 기다리는 중 (검색 중이거나, LLM이 참고 문서를 읽는 중)
  const waiting = message.status === "streaming" && !message.text;

  return (
    <div className="chat-msg assistant">
      <span className="copilot-avatar chat-avatar">AI</span>
      <div className="chat-body">
        {/* 1. 근거 문서 카드 (답변 위) - 근거가 없으면 아무것도 표시하지 않음 */}
        <SourceCards sources={sources} progress={message.progress} focus={focus} />

        {/* 2. 답변 말풍선 */}
        <div className="chat-bubble">
          {/* 기다리는 동안 "작성 중..." 문구 대신 진행 단계(① 검색 ② 문서 읽기 ③ 작성)를 표시
              - 첫 글자가 도착하면 타자 효과로 답변을 보여줌 (StreamingAnswer) */}
          {waiting && message.progress ? (
            <ChatProgressSteps progress={message.progress} />
          ) : (
            <StreamingAnswer text={message.text} streaming={message.status === "streaming"} onCitationClick={showSource} />
          )}
          {message.status === "error" && <Alert tone="error">{message.error}</Alert>}
          {message.status === "stopped" && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>(답변 생성을 중지했습니다)</div>}
        </div>

        {/* 3. 답변 정보 */}
        <div className="chat-meta">
          {/* 모델 이름 + 단계별 걸린 시간 표시 (예: qwen3.5:9b · 검색 0.6초 · 문서 읽기 6.3초 · 답변 작성 0.5초)
                */}
          {message.model && <span>{message.model}</span>}
          {message.progress && !waiting && <ChatProgressSummary progress={message.progress} />}
          {/* 이어서 묻는 질문을 다시 써서 검색했다면, 실제 검색어를 함께 표시 */}
          {message.searchQuery && <span title="이전 대화를 반영해서 다시 쓴 질문으로 검색했습니다">검색: “{message.searchQuery}”</span>}
        </div>
      </div>
    </div>
  );
}

export function ChatPage() {
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // 대화방 관련 상태
  const [conversationId, setConversationId] = useState<number | null>(null); // 지금 대화방 (새 대화면 null)
  const [conversations, setConversations] = useState<Conversation[]>([]); // 왼쪽 대화 목록
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false); // 예전 대화를 불러오는 중
  const [pageError, setPageError] = useState<string | null>(null); // 대화 열기/제목 변경 실패 등
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null); // 삭제 확인 중인 대화방
  const [deleting, setDeleting] = useState(false);
  // 주소의 ?conversation=3 (다른 화면이나 AI 창에서 특정 대화방을 열 때도 사용)
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedId = Number(searchParams.get("conversation")) || null;
  const openSeqRef = useRef(0); // 대화방을 빠르게 연달아 누를 때, 마지막에 누른 것만 화면에 반영하기 위한 번호
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState<ChatStatus | null>(null);
  const abortRef = useRef<AbortController | null>(null); // 진행 중인 요청을 취소하는 도구
  const nextIdRef = useRef(1); // 메시지 id 번호
  // bottomRef(맨 아래 표시용 빈 div) 대신 스크롤 상자 / 내용 영역 ref 사용
  const scrollRef = useRef<HTMLDivElement>(null); // 스크롤되는 바깥 상자
  const contentRef = useRef<HTMLDivElement>(null); // 높이 변화를 감지할 안쪽 내용

  // 1. LLM 연결 상태 확인 (화면이 열릴 때 한 번)
  useEffect(() => {
    getChatStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  // 2. 대화 내용의 높이가 바뀌면 맨 아래로 스크롤 (답변이 타자 효과로 길어지는 동안에도 계속 따라감)
  // 스크롤 기준을 "메시지 변경" -> "대화 내용 높이 변경"으로
  //  - ResizeObserver(크기 변화를 감지하는 브라우저 기능)로 높이가 바뀔 때마다 스크롤
  //  - 사용자가 위로 스크롤해서 예전 대화를 보고 있으면(맨 아래에서 150px 이상 위) 끌어내리지 않음
  useEffect(() => {
    const container = scrollRef.current;
    const content = contentRef.current;
    if (!container || !content) return;
    const observer = new ResizeObserver(() => {
      const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      if (distanceFromBottom < 150) container.scrollTop = container.scrollHeight;
    });
    observer.observe(content);
    return () => observer.disconnect(); // 화면이 사라지면 감지 중단
  }, []);

  // 3. 화면을 떠날 때 진행 중인 답변 요청 취소
  useEffect(() => () => abortRef.current?.abort(), []);

  // 4. 대화 목록 불러오기 (화면이 열릴 때 + 답변이 저장된 뒤)
  //  - useCallback: 함수를 매번 새로 만들지 않고 재사용 (useEffect의 의존성으로 쓰기 위함)
  const loadConversations = useCallback(async () => {
    setListLoading(true);
    try {
      const result = await listConversations();
      setConversations(result.items);
      setListError(null);
    } catch (error) {
      setListError(errorMessage(error));
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  // 5. 주소의 대화방 번호가 바뀌면 그 대화방 열기
  //  - 왼쪽 목록을 누르면 주소만 바꾸고(selectConversation), 실제로 여는 것은 여기서 함
  //    => 새로고침하거나 AI 창의 "챗봇 화면에서 이어서 보기"로 들어와도 똑같이 열림
  //  - 지금 열려 있는 대화방과 같은 번호면 다시 불러오지 않음
  //    (첫 질문의 답변이 끝나서 주소에 번호가 붙을 때 화면이 새로 그려지지 않도록)
  useEffect(() => {
    if (requestedId === null || requestedId === conversationId) return;
    const seq = ++openSeqRef.current;
    setOpening(true);
    setPageError(null);
    getConversation(requestedId)
      .then((detail) => {
        if (seq !== openSeqRef.current) return; // 그 사이에 다른 대화방을 눌렀으면 무시
        setConversationId(detail.id);
        setMessages(toChatMessages(detail.messages, () => nextIdRef.current++));
      })
      .catch((error) => {
        if (seq !== openSeqRef.current) return;
        // 삭제되었거나 다른 사람의 대화방 => 새 대화로 돌아감
        setPageError(errorMessage(error));
        setConversationId(null);
        setMessages([]);
        setSearchParams({}, { replace: true });
      })
      .finally(() => {
        if (seq === openSeqRef.current) setOpening(false);
      });
    // conversationId는 일부러 의존성에서 뺌: 주소(requestedId)가 바뀔 때만 실행되어야 함
  }, [requestedId]);

  // 대화방 선택 / 새 대화 / 제목 변경 / 삭제
  const selectConversation = (id: number) => setSearchParams({ conversation: String(id) });

  const startNewConversation = () => {
    openSeqRef.current++; // 불러오는 중인 대화방이 있으면 무시하도록
    setOpening(false);
    setPageError(null);
    setConversationId(null);
    setMessages([]);
    setSearchParams({});
  };

  const handleRename = async (id: number, title: string) => {
    try {
      const updated = await renameConversation(id, title);
      setConversations((current) => current.map((item) => (item.id === id ? updated : item)));
    } catch (error) {
      setPageError(errorMessage(error));
      throw error; // 목록 부품이 입력창을 닫지 않도록 실패를 알려줌
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteConversation(deleteTarget.id);
      setConversations((current) => current.filter((item) => item.id !== deleteTarget.id));
      // 지금 보고 있는 대화방을 지웠으면 새 대화로
      if (deleteTarget.id === conversationId) startNewConversation();
      setDeleteTarget(null);
    } catch (error) {
      setPageError(errorMessage(error));
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  // AI 답변 메시지 1개의 내용을 바꾸는 도우미
  const updateAssistant = (id: number, patch: (message: ChatMessage) => Partial<ChatMessage>) =>
    setMessages((current) => current.map((message) => (message.id === id ? { ...message, ...patch(message) } : message)));

  // 6. 질문 보내기
  // 지금 대화방 번호(conversation_id)를 함께 보내서 대화를 이어감 (새 대화면 보내지 않음)
  const ask = async (text: string) => {
    const question = text.trim();
    if (!question || streaming || opening) return;
    setPageError(null);
    const userId = nextIdRef.current++;
    const assistantId = nextIdRef.current++;
    // 질문을 보낸 시각부터 단계별 시각을 기록 (진행 단계 표시용)
    //  - progress에 시각을 추가하는 도우미: 기존 기록은 유지하고 새 값만 덧붙임
    const markProgress = (patch: Partial<ChatProgressTimes>) =>
      updateAssistant(assistantId, (message) => ({
        progress: { ...(message.progress ?? { startedAt: Date.now() }), ...patch },
      }));
    setMessages((current) => [
      ...current,
      { id: userId, role: "user", text: question },
      {
        id: assistantId,
        role: "assistant",
        text: "",
        status: "streaming",
        progress: { startedAt: Date.now() },
      },
    ]);
    setInput("");
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    let firstToken = true; // 첫 답변 조각인지 (= LLM이 참고 문서를 다 읽고 쓰기 시작한 순간)
    // 읽기 속도 보정용 - 근거 문서 도착 시각과 근거 문서 목록을 기억해 둠
    let sourcesAt: number | undefined;
    let receivedSources: ChatSource[] = [];

    try {
      await streamChat(
        { question, conversation_id: conversationId ?? undefined },
        {
          // 근거 문서 도착 => ① 검색 끝 시각 기록
          onSources: (sources) => {
            sourcesAt = Date.now();
            receivedSources = sources;
            updateAssistant(assistantId, () => ({ sources }));
            markProgress({ sourcesAt, sourceCount: sources.length });
          },
          // 답변 조각을 기존 글 뒤에 이어 붙임
          // 첫 조각 도착 => ② 문서 읽기 끝 시각 기록
          onToken: (piece) => {
            if (firstToken) {
              firstToken = false;
              const firstTokenAt = Date.now();
              markProgress({ firstTokenAt });
              // 실제로 문서를 읽는 데 걸린 시간으로 "읽는 중" 위치 계산용 읽기 속도를 보정
              if (sourcesAt !== undefined) recordReadingSpeed(sourcesAt, firstTokenAt, toSourceCardItems(receivedSources));
            }
            updateAssistant(assistantId, (message) => ({ text: message.text + piece }));
          },
          // 답변 끝 => ③ 답변 작성 끝 시각 기록 (기존: 서버가 준 전체 시간 elapsedMs 저장)
          // 답변이 저장된 대화방 번호를 기억 (다음 질문부터 이 대화방에 이어서 저장됨)
          //  - 첫 질문이면 서버가 새 대화방을 만들어서 번호를 알려줌 => 주소에도 붙이고 목록 새로고침
          //  - 검색에 사용한 질문이 원래 질문과 다르면(다시 쓴 질문) 답변 아래에 표시
          onDone: (info) => {
            updateAssistant(assistantId, () => ({
              status: "done",
              model: info.model,
              searchQuery: info.search_query !== question ? info.search_query : undefined,
            }));
            markProgress({ endedAt: Date.now() });
            setConversationId(info.conversation_id);
            setSearchParams({ conversation: String(info.conversation_id) }, { replace: true });
            loadConversations();
          },
          onError: (message) => {
            updateAssistant(assistantId, () => ({ status: "error", error: message }));
            markProgress({ endedAt: Date.now() });
          },
        },
        controller.signal,
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        // 사용자가 "중지"를 누른 경우
        updateAssistant(assistantId, () => ({ status: "stopped" }));
      } else {
        const message = error instanceof ApiError ? error.message : "답변 중 오류가 발생했습니다.";
        updateAssistant(assistantId, () => ({ status: "error", error: message }));
      }
      markProgress({ endedAt: Date.now() }); // 진행 시간 표시 멈춤
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    ask(input);
  };

  // Enter = 보내기, Shift + Enter = 줄바꿈
  //  - isComposing: 한글을 조합하는 중(예: "ㅎ" -> "하")에는 Enter로 보내지 않음 (한글 입력 버그 방지)
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      ask(input);
    }
  };

  return (
    <div className="page chat-page">
      <div className="page-header">
        <div className="page-title-row">
          <h1 className="page-title">챗봇</h1>
          <p className="page-desc">등록된 문서를 근거로 AI가 답변합니다. 답변의 번호를 누르면 근거 문서를 볼 수 있어요.</p>
        </div>
        {status ? (
          <Badge tone={status.available ? "success" : "danger"}>
            {status.model} · {status.available ? "연결됨" : "연결 안 됨"}
          </Badge>
        ) : (
          <Badge tone="neutral">LLM 상태 확인 중</Badge>
        )}
      </div>

      {status && !status.available && (
        <Alert tone="error">LLM 서버에 연결할 수 없어 답변을 만들 수 없습니다. {status.message}</Alert>
      )}

      {/* 대화 열기 / 제목 변경 / 삭제 실패 메시지 */}
      {pageError && <Alert tone="error">{pageError}</Alert>}

      {/* 왼쪽 대화 목록 + 오른쪽 대화 화면으로 나눔 (기존: 대화 화면만) */}
      <div className="chat-layout">
        <ConversationList
          conversations={conversations}
          activeId={conversationId}
          loading={listLoading}
          error={listError}
          disabled={streaming}
          onSelect={selectConversation}
          onNew={startNewConversation}
          onRename={handleRename}
          onDelete={setDeleteTarget}
        />

        <div className="card chat-card">
          {/* 1. 대화 내용 */}
          {/* 스크롤 상자(chat-messages) 안에 내용 영역(chat-messages-content)을 한 겹 두기
            - 내용 영역의 높이가 바뀌는 것을 감지해서 자동으로 맨 아래로 스크롤하기 위함 */}
          <div className="chat-messages" ref={scrollRef}>
            <div className="chat-messages-content" ref={contentRef}>
            {/* 예전 대화를 불러오는 중이면 불러오는 중 표시 */}
            {opening ? (
              <div className="empty">
                <Spinner size={20} />
                <span style={{ fontSize: 13 }}>대화를 불러오는 중...</span>
              </div>
            ) : messages.length === 0 ? (
              <div className="empty">
                <MessagesSquare size={30} />
                <strong>사내 문서에 대해 무엇이든 물어보세요</strong>
                <span style={{ fontSize: 13 }}>문서에 없는 내용은 "찾을 수 없습니다"라고 답합니다.</span>
                <div className="keyword-chips" style={{ justifyContent: "center", marginTop: 8 }}>
                  {SAMPLE_QUESTIONS.map((sample) => (
                    <button key={sample} type="button" className="chip" onClick={() => ask(sample)}>
                      {sample}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((message) =>
                message.role === "user" ? (
                  <div key={message.id} className="chat-msg user">
                    <div className="chat-body">
                      <div className="chat-meta" style={{ justifyContent: "flex-end" }}>
                        {user ? displayName(user.email) : "나"}
                      </div>
                      <div className="chat-bubble">{message.text}</div>
                    </div>
                  </div>
                ) : (
                  <AssistantMessage key={message.id} message={message} />
                ),
              )
            )}
            </div>
          </div>

          {/* 2. 입력창 */}
          <form className="chat-input" onSubmit={handleSubmit}>
            <textarea
              className="input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="질문을 입력하세요 (Enter: 보내기, Shift + Enter: 줄바꿈)"
              rows={2}
              maxLength={1000}
              aria-label="질문 입력"
            />
            {/*  예전 대화를 불러오는 중에는 보내기 버튼 비활성화 */}
            {streaming ? (
              <button type="button" className="btn btn-outline" onClick={() => abortRef.current?.abort()}>
                <Square size={14} /> 중지
              </button>
            ) : (
              <button type="submit" className="btn btn-primary" disabled={!input.trim() || opening}>
                <Send size={14} /> 보내기
              </button>
            )}
          </form>
          {/*  */}
          <div className="chat-footnote">
            같은 대화 안에서는 이전 대화를 참고해서 이어서 답합니다. 다른 주제는 "새 대화"로 시작하면 더 정확해요.
          </div>
        </div>
      </div>

      {/* 대화방 삭제 확인 창 (DocumentsPage의 문서 삭제 확인 창과 같은 방식) */}
      {deleteTarget && (
        <Modal
          title="대화 삭제"
          onClose={() => setDeleteTarget(null)}
          footer={
            <>
              <button type="button" className="btn btn-outline" onClick={() => setDeleteTarget(null)} disabled={deleting}>
                취소
              </button>
              <button type="button" className="btn btn-danger" onClick={handleDelete} disabled={deleting}>
                {deleting ? <Spinner size={14} /> : <Trash2 size={14} />} 삭제
              </button>
            </>
          }
        >
          <div className="form-stack">
            <p>
              <strong>{deleteTarget.title}</strong> 대화를 삭제할까요?
            </p>
            <Alert tone="warning">대화방 안의 질문과 답변이 모두 삭제되며 되돌릴 수 없습니다.</Alert>
          </div>
        </Modal>
      )}
    </div>
  );
}
