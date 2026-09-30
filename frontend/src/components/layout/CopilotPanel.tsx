// [수정] 새 파일 추가 - 오른쪽 AI Copilot 창
//  - 기존: 없음
//  - 변경: 작업 진행 상황 메시지와 대화 입력창을 보여주는 창 (접기 버튼으로 닫을 수 있음)
//    - 문서 업로드 등 다른 화면의 진행 상황이 메시지로 표시됨 (CopilotContext 참고)
//    - ⚠️ 아직 챗봇(LLM)이 연결되지 않아서, 질문을 보내면 안내 메시지로 답함
//      (④ 챗봇 단계에서 이 파일의 handleSend를 실제 답변 API 호출로 바꾸면 됨)

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
// [수정] 아이콘 import 변경
//  - 기존: PanelRightClose(접기), RotateCcw(대화 지우기) 사용
//  - 변경: 두 버튼을 없애고, 창 왼쪽 가운데의 접기 손잡이에 쓸 ChevronRight(">") 사용
import { Check, ChevronRight, CircleCheck, CircleX } from "lucide-react";

import { healthCheck } from "../../api/system";
import { useAuth } from "../../contexts/AuthContext";
import { useCopilot, type CopilotMessage } from "../../contexts/CopilotContext";
import { ROLE_LABELS, displayName, formatDateTime } from "../../utils/format";
import { Badge } from "../ui/Badge";
import { Spinner } from "../ui/Feedback";

// 추천 키워드 (누르면 바로 질문으로 보냄) - md 폴더의 테스트 문서 내용과 관련된 질문들
const RECOMMENDED_KEYWORDS = ["연차 사용 방법", "경조사비 지원 기준", "해고 예고 기간", "에이전트 시장 전망"];

// 질문에 대한 임시 답변 만들기 (챗봇 연결 전까지 사용)
//  - 질문에 특정 단어가 있으면 관련 화면으로 안내하고, 그 외에는 준비 중 안내
function buildPlaceholderReply(question: string): Omit<CopilotMessage, "id" | "createdAt"> {
  if (/업로드|등록|문서 추가/.test(question)) {
    return {
      sender: "ai",
      tone: "info",
      text: "문서는 [문서 관리] 화면에서 .txt, .md 파일을 올려 등록할 수 있어요. (관리자·매니저 권한 필요)",
      actions: [{ label: "문서 관리로 이동", to: "/documents" }],
    };
  }
  if (/승인|권한|가입/.test(question)) {
    return {
      sender: "ai",
      tone: "info",
      text: "회원가입한 계정은 관리자가 [사용자·권한 관리]에서 승인해야 로그인할 수 있어요.",
      actions: [{ label: "사용자·권한 관리로 이동", to: "/admin/users" }],
    };
  }
  return {
    sender: "ai",
    tone: "info",
    text: `"${question}"에 대한 답변 기능은 아직 연결되지 않았어요.\n등록된 문서를 근거로 답변하는 기능은 다음 단계에서 추가됩니다.`,
    details: ["③ 문서 검색: 질문과 비슷한 문서 청크 찾기", "④ 챗봇: 찾은 문서를 근거로 LLM이 답변"],
    actions: [{ label: "등록된 문서 보기", to: "/documents" }],
  };
}

// 메시지 앞에 붙는 상태 아이콘
function ToneIcon({ tone }: { tone: CopilotMessage["tone"] }) {
  if (tone === "success") return <CircleCheck size={18} color="#fff" fill="var(--success)" style={{ flexShrink: 0 }} />;
  if (tone === "error") return <CircleX size={18} color="#fff" fill="var(--danger)" style={{ flexShrink: 0 }} />;
  if (tone === "loading") return <Spinner size={16} />;
  return null;
}

export function CopilotPanel() {
  const { user } = useAuth();
  // [수정] clearMessages 제거 (대화 지우기 버튼을 없앴으므로 사용하지 않음)
  const { messages, pushMessage, setOpen } = useCopilot();
  const navigate = useNavigate();

  const [input, setInput] = useState("");
  const [online, setOnline] = useState<boolean | null>(null); // 백엔드 서버 상태 (null: 확인 중)
  const listRef = useRef<HTMLDivElement>(null);

  // 1. 서버 상태 확인 (창이 열릴 때 한 번)
  useEffect(() => {
    healthCheck()
      .then((result) => setOnline(result.status === "healthy"))
      .catch(() => setOnline(false));
  }, []);

  // 2. 새 메시지가 추가되면 맨 아래로 스크롤
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // 3. 질문 보내기
  const send = (text: string) => {
    const question = text.trim();
    if (!question) return;
    pushMessage({ sender: "user", text: question });
    setInput("");
    // 실제 답변처럼 보이도록 잠깐 기다렸다가 안내 메시지 추가
    window.setTimeout(() => pushMessage(buildPlaceholderReply(question)), 400);
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
      {/* [수정] 창 접기 버튼을 창 왼쪽 테두리 가운데의 ">" 손잡이로 변경
           - 기존: 제목 영역 오른쪽에 접기 아이콘 버튼(PanelRightClose)
           - 변경: 창 왼쪽 바깥으로 튀어나온 손잡이 버튼 (위치/모양은 global.css의 .copilot-collapse) */}
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
          <div className="copilot-subtitle">사내 문서 · 계정 관리 어시스턴트</div>
        </div>
        {online === null ? (
          <Badge tone="neutral">확인 중</Badge>
        ) : online ? (
          <Badge tone="success">온라인</Badge>
        ) : (
          <Badge tone="danger">오프라인</Badge>
        )}
        {/* [수정] 대화 지우기(RotateCcw) 버튼과 창 접기(PanelRightClose) 버튼 삭제
             - 기존: 상태 배지 오른쪽에 두 개의 아이콘 버튼이 있어 제목이 여러 줄로 좁아졌음
             - 변경: 두 버튼을 없애고, 접기는 창 왼쪽 가운데의 ">" 손잡이 버튼으로 대체 */}
      </div>

      {/* 2. 메시지 목록 */}
      <div className="copilot-messages" ref={listRef}>
        {messages.map((message) => (
          <div key={message.id} className={`msg ${message.sender === "user" ? "from-user" : ""}`}>
            <div className="msg-meta">
              {senderLabel(message)} ({formatDateTime(message.createdAt)})
            </div>
            <div className="msg-bubble">
              <div className={message.tone && message.tone !== "info" ? "msg-line" : undefined}>
                <ToneIcon tone={message.tone} />
                <span>{message.text}</span>
              </div>
              {message.details && message.details.length > 0 && (
                <ul className="msg-details">
                  {message.details.map((detail) => (
                    <li key={detail}>
                      <Check size={13} color="var(--success)" /> {detail}
                    </li>
                  ))}
                </ul>
              )}
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

      {/* 3. 추천 키워드 + 입력창 */}
      <div className="copilot-footer">
        <div className="keyword-title">추천 키워드</div>
        <div className="keyword-chips">
          {RECOMMENDED_KEYWORDS.map((keyword) => (
            <button key={keyword} type="button" className="chip" onClick={() => send(keyword)}>
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
          <button type="submit" className="btn btn-info" disabled={!input.trim()}>
            전송
          </button>
        </form>
      </div>
    </aside>
  );
}
