// 오른쪽 AI Copilot 창
//  - 작업 진행 상황 메시지와 대화 입력창을 보여주는 창 (접기 버튼으로 닫을 수 있음)
//    - 문서 업로드 등 다른 화면의 진행 상황이 메시지로 표시됨 (CopilotContext 참고)
//    - 질문을 보내면 챗봇 API(스트리밍)로 문서 근거 AI 답변 + 출처를 보여줌
//    - 근거 문서 카드를 답변 위에 표시 (챗봇 화면과 같은 SourceCards 부품 사용)
//    - 대화 이어가기: 이 창에서 한 질문들은 하나의 대화방에 이어서 저장됨
//      - "새 대화" 버튼을 누르면 새 대화방에서 다시 시작

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
// 창 왼쪽 가운데의 접기 손잡이에 쓸 ChevronRight(">") 사용
import { Check, ChevronRight, CircleCheck, CircleX } from "lucide-react";

// 문서 검색 API(searchDocuments) 대신 챗봇 스트리밍 API(streamChat) 사용
import { streamChat } from "../../api/chat";
import { ApiError } from "../../api/client";
import { healthCheck } from "../../api/system";
import { useAuth } from "../../contexts/AuthContext";
import { useCopilot, type CopilotMessage, type CopilotSource } from "../../contexts/CopilotContext";
import { ROLE_LABELS, displayName, formatDateTime } from "../../utils/format";
import { AnswerText } from "../chat/AnswerText";
import {
  ChatProgressSteps,
  ChatProgressSummary,
  StreamingAnswer,
  type ChatProgressTimes,
} from "../chat/ChatProgress";
// 근거 문서 카드 부품 (챗봇 화면과 같은 카드)
import { recordReadingSpeed, SourceCards, toSourceCardItems } from "../chat/SourceCards";
import { Badge } from "../ui/Badge";
import { Spinner } from "../ui/Feedback";

// 추천 키워드 (누르면 바로 질문으로 보냄) - md 폴더의 테스트 문서 내용과 관련된 질문들
const RECOMMENDED_KEYWORDS = ["연차 사용 방법", "경조사비 지원 기준", "해고 예고 기간", "에이전트 시장 전망"];


// 메시지 앞에 붙는 상태 아이콘
function ToneIcon({ tone }: { tone: CopilotMessage["tone"] }) {
  if (tone === "success") return <CircleCheck size={18} color="#fff" fill="var(--success)" style={{ flexShrink: 0 }} />;
  if (tone === "error") return <CircleX size={18} color="#fff" fill="var(--danger)" style={{ flexShrink: 0 }} />;
  if (tone === "loading") return <Spinner size={16} />;
  return null;
}

export function CopilotPanel() {
  const { user } = useAuth();
  // 대화방 번호(conversationId), 새 대화 시작(clearMessages)
  const { messages, pushMessage, updateMessage, setOpen, clearMessages, conversationId, setConversationId } =
    useCopilot();
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  // 답변을 만드는 중인지
  //  - 답변이 끝나기 전에 다음 질문을 보내면 대화방 번호가 정해지기 전이라 대화가 둘로 갈라짐
  //    => 답변 중에는 전송 버튼과 추천 키워드를 잠깐 막음
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState<boolean | null>(null); // 백엔드 서버 상태 (null: 확인 중)
  const listRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // 1. 서버 상태 확인 (창이 열릴 때 한 번)
  useEffect(() => {
    healthCheck()
      .then((result) => setOnline(result.status === "healthy"))
      .catch(() => setOnline(false));
  }, []);

  // 2. 메시지 내용의 높이가 바뀌면 맨 아래로 스크롤
  //  - 스크롤 기준을 "메시지 변경" -> "내용 높이 변경"으로 변경 (챗봇 화면과 같은 방식)
  //  - 사용자가 위로 스크롤해서 예전 메시지를 보고 있으면(맨 아래에서 150px 이상 위) 끌어내리지 않음
  useEffect(() => {
    const container = listRef.current;
    const content = contentRef.current;
    if (!container || !content) return;
    const observer = new ResizeObserver(() => {
      const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      if (distanceFromBottom < 150) container.scrollTop = container.scrollHeight;
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  // 3. 질문 보내기
  // 문서 검색 결과 대신 챗봇 AI 답변(스트리밍)으로 답하도록
  //  - "찾는 중..." -> 챗봇 스트리밍 API
  //    -> 근거 문서 도착 시 출처 카드 표시 -> 답변 조각이 올 때마다 글을 이어 붙임
  const send = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    setBusy(true);
    pushMessage({ sender: "user", text: question });
    setInput("");
    // "찾는 중..." 문구 + 로딩 아이콘 대신, 진행 단계(검색 -> 문서 읽기 -> 작성)를 보여줌
    //  - progress: 단계별 시각 기록 (화면에서 직접 시간을 잼)
    let progress: ChatProgressTimes = { startedAt: Date.now() };
    const messageId = pushMessage({ sender: "ai", tone: "info", text: "", streaming: true, progress });
    let answer = ""; // 지금까지 받은 답변 (조각을 계속 이어 붙임)
    let cardSources: CopilotSource[] = []; // 받은 근거 문서 (읽기 속도 보정용)
    // 진행 시각 기록 도우미: 기존 기록에 새 시각을 덧붙여서 메시지에 반영
    const markProgress = (patch: Partial<ChatProgressTimes>) => {
      progress = { ...progress, ...patch };
      updateMessage(messageId, { progress });
    };

    try {
      // 지금 대화방 번호를 함께 보내서 대화를 이어감 (첫 질문이면 보내지 않음)
      await streamChat(
        { question, conversation_id: conversationId ?? undefined },
        {
          // 3-1. 근거 문서 도착 => 출처 카드 표시 + ① 검색 끝 시각 기록
          // 출처 카드 정보 형식
          //  - 챗봇 화면과 같은 카드 정보 (번호, 파일명, 청크 번호, 원문 전체, 유사도)
          onSources: (sources) => {
            cardSources = toSourceCardItems(sources);
            updateMessage(messageId, { sources: cardSources });
            markProgress({ sourcesAt: Date.now(), sourceCount: sources.length });
          },
          // 3-2. 답변 조각 도착 => 글을 이어 붙임 (첫 조각이면 ② 문서 읽기 끝 시각 기록)
          onToken: (piece) => {
            if (!answer) {
              markProgress({ firstTokenAt: Date.now() });
              // 실제로 문서를 읽는 데 걸린 시간으로 "읽는 중" 위치 계산용 읽기 속도를 보정
              if (progress.sourcesAt !== undefined && progress.firstTokenAt !== undefined) {
                recordReadingSpeed(progress.sourcesAt, progress.firstTokenAt, cardSources);
              }
            }
            answer += piece;
            updateMessage(messageId, { text: answer });
          },
          // 3-3. 답변 끝 => ③ 작성 끝 시각 기록, 근거 문서를 더 자세히 볼 수 있는 버튼
          //  * 대화방 번호 저장 + "챗봇 화면에서 이어 보기" 버튼
          //  - 검색 결과 보기는 실제 검색에 사용한 질문(이어서 묻는 질문이면 다시 쓴 질문)으로 이동
          onDone: (info) => {
            markProgress({ endedAt: Date.now() });
            setConversationId(info.conversation_id);
            updateMessage(messageId, {
              streaming: false,
              // encodeURIComponent: 한글/공백/특수문자를 주소에 넣을 수 있는 형식으로 바꿈
              actions: [
                { label: "근거 문서 검색 결과 보기", to: `/search?q=${encodeURIComponent(info.search_query)}` },
                { label: "챗봇 화면에서 이어 보기", to: `/chat?conversation=${info.conversation_id}` },
              ],
            });
          },
          // 3-4. 답변 도중 장애
          onError: (message) => {
            markProgress({ endedAt: Date.now() });
            updateMessage(messageId, { tone: "error", text: message, streaming: false });
          },
        },
      );
    } catch (error) {
      // 스트리밍 시작 전 에러 (예: 로그인 만료, 임베딩 서버 장애 503)
      markProgress({ endedAt: Date.now() });
      updateMessage(messageId, {
        tone: "error",
        text: error instanceof ApiError ? error.message : "답변 중 오류가 발생했습니다.",
        streaming: false,
      });
    } finally {
      setBusy(false); // 답변이 끝나면(성공/실패 모두) 다시 질문할 수 있게 함
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault(); // 폼 제출 시 페이지가 새로고침되는 기본 동작을 막음
    send(input);
  };

  // 메시지 위에 표시할 보낸 사람 이름 (예: "sujin.han 매니저")
  const senderLabel = (message: CopilotMessage) =>
    message.sender === "ai" ? "AI Copilot" : user ? `${displayName(user.email)} ${ROLE_LABELS[user.role]}` : "나";

  return (
    <aside className="copilot-panel" aria-label="AI Copilot">
      {/* 창 접기 버튼을 창 왼쪽 테두리 가운데의 ">" 손잡이
           - 창 왼쪽 바깥으로 튀어나온 손잡이 버튼 (위치/모양은 global.css의 .copilot-collapse) */}
      <button
        type="button"
        className="copilot-collapse"
        onClick={() => setOpen(false)}
        title="AI 창 접기"
        aria-label="AI 창 접기"
      >
        <ChevronRight size={14} />
      </button>

      {/* 1. 제목 영역 */}
      <div className="copilot-header">
        <span className="copilot-avatar">AI</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="copilot-title">
            ONGYEOL <span className="accent">AI</span> Copilot
          </div>
          {/*  */}
          <div className="copilot-subtitle">사내 문서 기반 AI 어시스턴트</div>
        </div>
        {online === null ? (
          <Badge tone="neutral">확인 중</Badge>
        ) : online ? (
          <Badge tone="success">온라인</Badge>
        ) : (
          <Badge tone="danger">오프라인</Badge>
        )}
        {/*  */}
      </div>

      {/* 2. 메시지 목록 */}
      {/* 스크롤 상자 안에 내용 영역(copilot-messages-content)을 한 겹 두기 (자동 스크롤용) */}
      <div className="copilot-messages" ref={listRef}>
        <div className="copilot-messages-content" ref={contentRef}>
        {messages.map((message) => (
          <div key={message.id} className={`msg ${message.sender === "user" ? "from-user" : ""}`}>
            <div className="msg-meta">
              {senderLabel(message)} ({formatDateTime(message.createdAt)})
            </div>
            <div className="msg-bubble">
              {/* 근거 문서 카드를 답변 위로
                   - 답변 위에 근거 문서 카드 (유사도 캡슐, "자세히 보기"로 원문 펼치기,
                     읽는 중인 문서는 빨간 테두리) */}
              {message.sources && message.sources.length > 0 && (
                <SourceCards sources={message.sources} progress={message.progress} />
              )}
              <div className={message.tone && message.tone !== "info" ? "msg-line" : undefined}>
                <ToneIcon tone={message.tone} />
                {/* AI 메시지 표시 방식
                     - 챗봇 답변(progress 있음): 첫 글자 전에는 진행 단계, 이후에는 타자 효과 답변
                     - 알림 메시지(업로드 완료 등): 지금처럼 전체 글을 바로 표시 (AnswerText)
                     - 사용자 메시지: 글자 그대로 표시 */}
                {message.sender === "user" ? (
                  <span>{message.text}</span>
                ) : message.progress && message.streaming && !message.text ? (
                  <ChatProgressSteps progress={message.progress} />
                ) : message.progress ? (
                  <StreamingAnswer text={message.text} streaming={Boolean(message.streaming)} />
                ) : (
                  <AnswerText text={message.text} streaming={message.streaming} />
                )}
              </div>
              {/* 챗봇 답변 아래에 단계별 걸린 시간 표시 (예: 검색 0.6초 · 문서 읽기 6.3초 · 답변 작성 0.5초) */}
              {message.progress && message.text && (
                <div className="msg-progress">
                  <ChatProgressSummary progress={message.progress} />
                </div>
              )}
              {message.details && message.details.length > 0 && (
                <ul className="msg-details">
                  {message.details.map((detail) => (
                    <li key={detail}>
                      <Check size={13} color="var(--success)" /> {detail}
                    </li>
                  ))}
                </ul>
              )}
              {/* 답변 아래의 출처 카드(.msg-sources) 삭제 => 답변 위의 SourceCards로 이동 */}
              {message.actions && message.actions.length > 0 && (
                <div className="msg-actions">
                  {message.actions.map((action) => (
                    <button key={action.label} type="button" className="btn btn-dark btn-sm" onClick={() => navigate(action.to)}>
                      {action.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        </div>
      </div>

      {/* 3. 추천 키워드 + 입력창 */}
      <div className="copilot-footer">
        {/* 대화 중이면 오른쪽에 "새 대화" 버튼 표시 (누르면 메시지를 지우고 새 대화로 시작) */}
        <div className="keyword-title" style={{ display: "flex", justifyContent: "space-between" }}>
          <span>추천 키워드</span>
          {conversationId !== null && (
            <button type="button" className="link-button" onClick={clearMessages} disabled={busy}>
              새 대화
            </button>
          )}
        </div>
        <div className="keyword-chips">
          {RECOMMENDED_KEYWORDS.map((keyword) => (
            <button key={keyword} type="button" className="chip" onClick={() => send(keyword)} disabled={busy}>
              {keyword}
            </button>
          ))}
        </div>
        <form className="copilot-input" onSubmit={handleSubmit}>
          <input
            className="input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="사내 규정이나 문서에 대해 질문하세요..."
            aria-label="AI에게 질문하기"
          />
          <button type="submit" className="btn btn-info" disabled={!input.trim() || busy}>
            전송
          </button>
        </form>
      </div>
    </aside>
  );
}
