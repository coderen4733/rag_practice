// [수정] 새 파일 추가 - 안내 메시지 / 빈 목록 / 로딩 표시 부품
//  - 기존: 없음
//  - 변경: 여러 화면에서 반복되는 "상태 표시" 화면 조각을 모아둠

import type { ReactNode } from "react";
import { CircleAlert, CircleCheck, Info, LoaderCircle, TriangleAlert } from "lucide-react";

// ───────────── 1. 안내 메시지 박스 ─────────────
type AlertTone = "error" | "success" | "info" | "warning";

const ALERT_ICONS = {
  error: CircleAlert,
  success: CircleCheck,
  info: Info,
  warning: TriangleAlert,
};

// 사용법: <Alert tone="error">이미 존재하는 이메일입니다.</Alert>
export function Alert({ tone = "info", children }: { tone?: AlertTone; children: ReactNode }) {
  const Icon = ALERT_ICONS[tone];
  return (
    <div className={`alert alert-${tone}`} role={tone === "error" ? "alert" : "status"}>
      <Icon size={16} style={{ flexShrink: 0, marginTop: 1 }} />
      {/* whiteSpace: 여러 줄 에러 메시지(\n)를 줄바꿈해서 보여줌 */}
      <div style={{ whiteSpace: "pre-line" }}>{children}</div>
    </div>
  );
}

// ───────────── 2. 로딩 아이콘 ─────────────
// 사용법: <Spinner /> 또는 <Spinner size={14} />
export function Spinner({ size = 16 }: { size?: number }) {
  return <LoaderCircle size={size} className="spin" aria-label="불러오는 중" />;
}

// ───────────── 3. 빈 목록 / 로딩 중 표시 ─────────────
// 사용법: <EmptyState icon={<FileText />} title="등록된 문서가 없습니다." />
export function EmptyState({
  icon,
  title,
  description,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
}) {
  return (
    <div className="empty">
      {icon}
      <strong>{title}</strong>
      {description && <span style={{ fontSize: 13 }}>{description}</span>}
    </div>
  );
}
