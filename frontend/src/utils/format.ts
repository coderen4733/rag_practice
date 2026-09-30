// [수정] 새 파일 추가 - 화면에 보여줄 값의 형식을 바꾸는 도우미 함수 모음
//  - 기존: 없음
//  - 변경: 날짜, 파일 크기, 권한/상태 이름을 사람이 읽기 좋은 한국어로 바꿈

import type { DocumentStatus, Role } from "../api/types";

// 두 자리 숫자로 만들기 (예: 9 => "09")
const pad = (value: number) => String(value).padStart(2, "0");

// 날짜/시간 => "2026.09.30. 14:46:26"
export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "-";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "-";
  return (
    `${date.getFullYear()}.${pad(date.getMonth() + 1)}.${pad(date.getDate())}. ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

// 날짜만 => "2026.09.30."
export function formatDate(value: string | null | undefined): string {
  return formatDateTime(value).split(" ")[0];
}

// 파일 크기(바이트) => "24.9 KB"
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

// 숫자에 천 단위 쉼표 => 12,588
export function formatNumber(value: number): string {
  return value.toLocaleString("ko-KR");
}

// 권한 => 한국어 이름
export const ROLE_LABELS: Record<Role, string> = {
  admin: "관리자",
  manager: "매니저",
  user: "사용자",
};

// 문서 처리 상태 => 한국어 이름 + 배지 색상
export const DOCUMENT_STATUS: Record<DocumentStatus, { label: string; tone: BadgeTone }> = {
  processing: { label: "처리 중", tone: "warning" },
  completed: { label: "처리 완료", tone: "success" },
  failed: { label: "처리 실패", tone: "danger" },
};

// 배지 색상 종류 (global.css의 .badge-xxx 와 이름이 같음)
export type BadgeTone = "success" | "danger" | "warning" | "info" | "brand" | "neutral";

// 이메일 => 화면 표시용 이름 (예: "sujin.han@corp.com" => "sujin.han")
export function displayName(email: string): string {
  return email.split("@")[0];
}
