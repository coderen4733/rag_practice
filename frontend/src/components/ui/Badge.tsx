// 상태 배지 (예: "처리 완료", "승인 대기")
//  - tone(색상)에 따라 global.css의 .badge-xxx 스타일을 적용하는 작은 부품

import type { ReactNode } from "react";

import type { BadgeTone } from "../../utils/format";

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
}

// 사용법: <Badge tone="success">처리 완료</Badge>
export function Badge({ tone = "neutral", children }: BadgeProps) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
