// [수정] 새 파일 추가 - 오른쪽 AI Copilot 창 상태 관리
//  - 기존: 없음
//  - 변경: AI 창의 열림/닫힘 상태와 대화 메시지 목록을 모든 화면에서 사용할 수 있게 함
//    - 다른 화면(문서 업로드 등)에서 pushMessage()로 진행 상황을 AI 창에 알릴 수 있음
//    - 예) 업로드 시작 -> "처리 중..." 메시지 추가 -> 완료 후 updateMessage()로 "완료"로 변경
//  - ⚠️ 아직 챗봇(LLM) 기능이 없어서, 사용자가 입력한 질문에는 안내 메시지로만 답함
//    (④ 챗봇 단계에서 실제 답변 API와 연결 예정)

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

// 메시지 안의 버튼 (누르면 해당 주소로 이동)
export interface CopilotAction {
  label: string;
  to: string;
}

// 메시지 1개
export interface CopilotMessage {
  id: string;
  sender: "ai" | "user";
  text: string;
  // 메시지 앞에 붙는 상태 아이콘 (success: 초록 체크, error: 빨간 X, loading: 회전 아이콘)
  tone?: "info" | "success" | "error" | "loading";
  details?: string[]; // 아래에 붙는 세부 항목 목록
  actions?: CopilotAction[];
  createdAt: Date;
}

// 새 메시지를 추가할 때 넘기는 값 (id, 시간은 자동으로 채움)
export type NewCopilotMessage = Omit<CopilotMessage, "id" | "createdAt">;

interface CopilotContextValue {
  isOpen: boolean;
  setOpen: (open: boolean) => void;
  toggleOpen: () => void;
  messages: CopilotMessage[];
  pushMessage: (message: NewCopilotMessage) => string;
  updateMessage: (id: string, patch: Partial<NewCopilotMessage>) => void;
  clearMessages: () => void;
}

const OPEN_KEY = "rag.copilotOpen"; // AI 창 열림 상태를 저장할 때 쓰는 이름

// 메시지 id를 만들 때 쓰는 번호 (1씩 늘어남)
//  - crypto.randomUUID()는 HTTPS 또는 localhost에서만 동작해서 사용하지 않음
//    (폐쇄망 고객사에서 http://10.x.x.x 처럼 접속하면 동작하지 않기 때문)
let messageSequence = 0;
function createMessageId(): string {
  messageSequence += 1;
  return `msg-${Date.now()}-${messageSequence}`;
}

const CopilotContext = createContext<CopilotContextValue | null>(null);

// 처음 보여줄 인사 메시지
function welcomeMessage(): CopilotMessage {
  return {
    id: "welcome",
    sender: "ai",
    tone: "info",
    text: "안녕하세요! ONGYEOL AI Copilot입니다.\n문서 등록, 사용자 관리 등 작업 진행 상황을 이 창에서 알려드려요.",
    actions: [{ label: "문서 관리로 이동", to: "/documents" }],
    createdAt: new Date(),
  };
}

// 저장된 열림 상태 읽기 (저장된 값이 없으면 열린 상태로 시작)
function getInitialOpen(): boolean {
  try {
    return localStorage.getItem(OPEN_KEY) !== "false";
  } catch {
    return true;
  }
}

export function CopilotProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState<boolean>(getInitialOpen);
  const [messages, setMessages] = useState<CopilotMessage[]>(() => [welcomeMessage()]);

  // 열림 상태가 바뀌면 저장 (새로고침해도 유지)
  useEffect(() => {
    try {
      localStorage.setItem(OPEN_KEY, String(isOpen));
    } catch {
      // 무시
    }
  }, [isOpen]);

  const setOpen = useCallback((open: boolean) => setIsOpen(open), []);
  const toggleOpen = useCallback(() => setIsOpen((current) => !current), []);

  // 메시지 추가 => 추가한 메시지의 id를 돌려줌 (나중에 updateMessage로 내용을 바꿀 때 사용)
  const pushMessage = useCallback((message: NewCopilotMessage) => {
    const id = createMessageId();
    setMessages((current) => [...current, { ...message, id, createdAt: new Date() }]);
    return id;
  }, []);

  // 메시지 내용 바꾸기 (예: "처리 중..." -> "처리 완료")
  const updateMessage = useCallback((id: string, patch: Partial<NewCopilotMessage>) => {
    setMessages((current) =>
      current.map((message) =>
        message.id === id ? { ...message, ...patch, createdAt: new Date() } : message,
      ),
    );
  }, []);

  const clearMessages = useCallback(() => setMessages([welcomeMessage()]), []);

  const value = useMemo<CopilotContextValue>(
    () => ({ isOpen, setOpen, toggleOpen, messages, pushMessage, updateMessage, clearMessages }),
    [isOpen, setOpen, toggleOpen, messages, pushMessage, updateMessage, clearMessages],
  );

  return <CopilotContext.Provider value={value}>{children}</CopilotContext.Provider>;
}

// 사용법: const { pushMessage, updateMessage } = useCopilot();
export function useCopilot(): CopilotContextValue {
  const context = useContext(CopilotContext);
  if (!context) throw new Error("useCopilot은 CopilotProvider 안에서만 사용할 수 있습니다.");
  return context;
}
