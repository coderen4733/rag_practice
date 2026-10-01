//  * 대화방 목록 (챗봇 화면 왼쪽)
//  - 내 대화방 목록을 최근 대화 순으로 보여줌
//    - "새 대화" 버튼: 이전 대화와 상관없는 새 대화 시작
//    - 대화방을 누르면 그 대화를 다시 열어서 이어서 질문할 수 있음
//    - 연필 버튼: 제목 바꾸기 (Enter: 저장, Esc: 취소) / 휴지통 버튼: 삭제 (확인 창은 챗봇 화면이 띄움)

import { useState, type KeyboardEvent } from "react";
import { Check, MessageSquarePlus, Pencil, Trash2, X } from "lucide-react";

import type { Conversation } from "../../api/types";
import { formatDateTime } from "../../utils/format";
import { Spinner } from "../ui/Feedback";

interface ConversationListProps {
  conversations: Conversation[];
  activeId: number | null; // 지금 열려 있는 대화방 (새 대화면 null)
  loading: boolean; // 목록을 불러오는 중
  error: string | null; // 목록 불러오기 실패 메시지
  disabled: boolean; // 답변을 만드는 중에는 다른 대화방으로 바꿀 수 없음
  onSelect: (conversationId: number) => void;
  onNew: () => void;
  onRename: (conversationId: number, title: string) => Promise<void>;
  onDelete: (conversation: Conversation) => void;
}

export function ConversationList({
  conversations,
  activeId,
  loading,
  error,
  disabled,
  onSelect,
  onNew,
  onRename,
  onDelete,
}: ConversationListProps) {
  // 제목을 바꾸는 중인 대화방 id와 입력값
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [saving, setSaving] = useState(false);

  // 제목 바꾸기 시작
  const startEdit = (conversation: Conversation) => {
    setEditingId(conversation.id);
    setEditingTitle(conversation.title);
  };

  // 제목 저장 (빈 제목이거나 바뀌지 않았으면 저장하지 않고 닫기)
  const saveEdit = async (conversation: Conversation) => {
    const title = editingTitle.trim();
    if (!title || title === conversation.title) {
      setEditingId(null);
      return;
    }
    setSaving(true);
    try {
      await onRename(conversation.id, title);
      setEditingId(null);
    } catch {
      // 실패하면 입력창을 그대로 두어 다시 시도할 수 있게 함 (에러 메시지는 챗봇 화면이 보여줌)
    } finally {
      setSaving(false);
    }
  };

  // Enter = 저장, Esc = 취소 (한글 조합 중 Enter는 무시)
  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>, conversation: Conversation) => {
    if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      event.preventDefault();
      saveEdit(conversation);
    }
    if (event.key === "Escape") setEditingId(null);
  };

  return (
    <aside className="card conversation-panel" aria-label="대화 목록">
      {/* 1. 새 대화 버튼 */}
      <div className="conversation-panel-head">
        <button type="button" className="btn btn-outline btn-block" onClick={onNew} disabled={disabled}>
          <MessageSquarePlus size={15} /> 새 대화
        </button>
      </div>

      {/* 2. 대화방 목록 */}
      <div className="conversation-items">
        {loading && conversations.length === 0 ? (
          <div className="conversation-empty">
            <Spinner size={14} /> 불러오는 중...
          </div>
        ) : error ? (
          <div className="conversation-empty error">{error}</div>
        ) : conversations.length === 0 ? (
          <div className="conversation-empty">아직 대화가 없습니다.</div>
        ) : (
          conversations.map((conversation) =>
            editingId === conversation.id ? (
              // 2-1. 제목 바꾸는 중
              <div key={conversation.id} className="conversation-item editing">
                <input
                  className="input"
                  value={editingTitle}
                  onChange={(event) => setEditingTitle(event.target.value)}
                  onKeyDown={(event) => handleKeyDown(event, conversation)}
                  maxLength={100}
                  autoFocus
                  disabled={saving}
                  aria-label="대화방 제목"
                />
                <button type="button" className="conversation-action" onClick={() => saveEdit(conversation)} disabled={saving} title="저장" aria-label="제목 저장">
                  {saving ? <Spinner size={13} /> : <Check size={14} />}
                </button>
                <button type="button" className="conversation-action" onClick={() => setEditingId(null)} disabled={saving} title="취소" aria-label="제목 바꾸기 취소">
                  <X size={14} />
                </button>
              </div>
            ) : (
              // 2-2. 평소 모습: 제목 + 마지막 대화 시각, 마우스를 올리면 연필/휴지통 버튼
              <div key={conversation.id} className={`conversation-item ${conversation.id === activeId ? "active" : ""}`}>
                <button
                  type="button"
                  className="conversation-open"
                  onClick={() => onSelect(conversation.id)}
                  disabled={disabled}
                  title={conversation.title}
                >
                  <span className="conversation-title">{conversation.title}</span>
                  <span className="conversation-date">{formatDateTime(conversation.updated_at)}</span>
                </button>
                <div className="conversation-actions">
                  <button type="button" className="conversation-action" onClick={() => startEdit(conversation)} disabled={disabled} title="제목 바꾸기" aria-label="제목 바꾸기">
                    <Pencil size={13} />
                  </button>
                  <button type="button" className="conversation-action danger" onClick={() => onDelete(conversation)} disabled={disabled} title="삭제" aria-label="대화방 삭제">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ),
          )
        )}
      </div>
    </aside>
  );
}
