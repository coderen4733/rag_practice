// [수정] 새 파일 추가 - 팝업 창 (모달)
//  - 기존: 없음
//  - 변경: 화면 위에 겹쳐서 뜨는 창 (예: 사용자 생성, 문서 상세, 삭제 확인)
//    - 바깥(어두운 배경)을 누르거나 ESC 키를 누르면 닫힘

import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode; // 아래쪽 버튼 영역
  width?: number; // 창 최대 너비 (기본 480px)
}

export function Modal({ title, onClose, children, footer, width }: ModalProps) {
  // ESC 키를 누르면 닫기
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    // 어두운 배경을 누르면 닫기
    <div className="modal-backdrop" onMouseDown={onClose}>
      {/* stopPropagation: 창 "안쪽"을 눌렀을 때는 닫히지 않도록 배경으로 클릭이 전달되는 것을 막음 */}
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={width ? { maxWidth: width } : undefined}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <span>{title}</span>
          <button type="button" className="icon-button" onClick={onClose} aria-label="닫기">
            <X size={18} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
