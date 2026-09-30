// [수정] 새 파일 추가 - 백엔드 API 호출 공통 함수
//  - 기존: 없음
//  - 변경: 모든 API 요청이 이 파일의 request() 함수를 거치도록 함
//    1) 주소 앞에 "/api"를 붙이고, 로그인 토큰(Authorization 헤더)을 자동으로 넣음
//    2) 액세스 토큰이 만료되어 401이 오면 => 리프레시 토큰으로 재발급 후 "한 번 더" 요청
//    3) 재발급도 실패하면 => 저장된 토큰을 지우고 "로그인 만료" 이벤트를 알림
//    4) 에러 응답은 사람이 읽을 수 있는 한국어 메시지로 바꿔서 ApiError로 던짐

import type { ApiResponse } from "./types";

// API 기본 주소: 개발 중에는 "/api" => vite.config.ts의 프록시가 백엔드(8000)로 전달
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

// 브라우저 저장소(localStorage)에 토큰을 저장할 때 쓰는 이름
const ACCESS_TOKEN_KEY = "rag.accessToken";
const REFRESH_TOKEN_KEY = "rag.refreshToken";

// 로그인이 만료되었을 때 발생시키는 이벤트 이름 (AuthContext가 듣고 있다가 로그아웃 처리)
export const AUTH_EXPIRED_EVENT = "auth:expired";

// ───────────── 1. 토큰 저장소 ─────────────
//  - localStorage: 브라우저를 껐다 켜도 남아 있는 저장 공간
//  - ⚠️ 개발/테스트 편의를 위한 방식. 실제 서비스에서는 보안을 위해 HttpOnly 쿠키를 권장
//  - try/catch: 브라우저 설정(시크릿 모드 등)에 따라 localStorage 사용이 막혀 있을 수 있음
export const tokenStorage = {
  getAccess(): string | null {
    try {
      return localStorage.getItem(ACCESS_TOKEN_KEY);
    } catch {
      return null;
    }
  },
  getRefresh(): string | null {
    try {
      return localStorage.getItem(REFRESH_TOKEN_KEY);
    } catch {
      return null;
    }
  },
  save(accessToken: string, refreshToken?: string): void {
    try {
      localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
      if (refreshToken) localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
    } catch {
      // 저장할 수 없는 환경이면 무시 (새로고침하면 다시 로그인해야 함)
    }
  },
  clear(): void {
    try {
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
    } catch {
      // 무시
    }
  },
};

// ───────────── 2. API 에러 ─────────────
//  - status: HTTP 상태 코드 (0이면 서버에 연결 자체가 안 된 경우)
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// ───────────── 3. 요청 옵션 ─────────────
type QueryValue = string | number | boolean | null | undefined;

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown; // JSON으로 보낼 데이터
  form?: FormData; // 파일 업로드처럼 multipart/form-data로 보낼 데이터
  query?: Record<string, QueryValue>; // 주소 뒤 ?a=1&b=2 에 붙일 값
  auth?: boolean; // 로그인 토큰을 넣을지 (로그인/회원가입 API는 false)
  retried?: boolean; // 토큰 재발급 후 다시 보낸 요청인지 (무한 반복 방지용, 내부에서만 사용)
}

// 주소 만들기: "/users/" + { page: 2, role: undefined } => "/api/users/?page=2"
//  - 값이 비어 있는(undefined, null, "") 항목은 주소에 넣지 않음
function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.append(key, String(value));
    }
  });
  const queryString = params.toString();
  return `${API_BASE}${path}${queryString ? `?${queryString}` : ""}`;
}

// ───────────── 4. 공통 요청 함수 ─────────────
//  - 사용법: const res = await request<ApiResponse<User>>("/users/me")
//  - T: 응답 JSON 전체의 타입
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, form, query, auth = true } = options;

  // 4-1. 요청 헤더 만들기
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const accessToken = tokenStorage.getAccess();
  if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`;

  // 4-2. 요청 보내기
  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      // FormData는 브라우저가 Content-Type(경계값 포함)을 자동으로 넣어주므로 직접 지정하지 않음
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
    });
  } catch {
    // 네트워크 에러: 백엔드 서버가 꺼져 있거나 주소가 틀린 경우
    throw new ApiError(0, "서버에 연결할 수 없습니다. 백엔드 서버가 켜져 있는지 확인하세요.");
  }

  // 4-3. 401(로그인 필요/토큰 만료) => 토큰 재발급 후 한 번만 다시 요청
  if (response.status === 401 && auth && tokenStorage.getRefresh()) {
    if (!options.retried && (await refreshAccessToken())) {
      return request<T>(path, { ...options, retried: true });
    }
    // 재발급 실패 또는 재발급 후에도 401 => 로그인 만료 처리
    notifySessionExpired();
  }

  // 4-4. 응답 읽기 (본문이 비어 있거나 JSON이 아닐 수도 있음)
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, extractErrorMessage(payload, response.status));
  }
  return payload as T;
}

// 응답의 data 꺼내기 (data가 비어 있으면 에러)
export function unwrap<T>(response: ApiResponse<T>): T {
  if (response.data === null || response.data === undefined) {
    throw new ApiError(500, "서버 응답에 데이터가 없습니다.");
  }
  return response.data;
}

// ───────────── 5. 토큰 재발급 ─────────────
//  - 여러 API가 "동시에" 401을 받아도 재발급 요청은 딱 한 번만 보내도록 함
//    (진행 중인 재발급이 있으면 그 결과를 함께 기다림)
let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refreshToken = tokenStorage.getRefresh();
      if (!refreshToken) return false;
      try {
        const response = await fetch(buildUrl("/auth/re-token"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!response.ok) return false;
        const json = (await response.json()) as ApiResponse<{ access_token: string }>;
        if (!json.data) return false;
        tokenStorage.save(json.data.access_token); // 새 액세스 토큰 저장
        return true;
      } catch {
        return false;
      } finally {
        // 다음 번 만료 때 다시 재발급할 수 있도록 초기화
        refreshPromise = null;
      }
    })();
  }
  return refreshPromise;
}

// 로그인 만료 알림: 토큰을 지우고 이벤트 발생 (AuthContext가 로그인 화면으로 보냄)
function notifySessionExpired(): void {
  tokenStorage.clear();
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
}

// ───────────── 6. 에러 메시지 만들기 ─────────────
// 입력값 이름 -> 화면에 보여줄 한국어 이름
const FIELD_LABELS: Record<string, string> = {
  email: "이메일",
  password: "비밀번호",
  password_confirm: "비밀번호 확인",
  current_password: "현재 비밀번호",
  new_password: "새 비밀번호",
  new_password_confirm: "새 비밀번호 확인",
  role: "권한",
  is_active: "활성화 여부",
  page: "페이지",
  size: "페이지 크기",
  sort_by: "정렬 기준",
  order: "정렬 방향",
  status: "상태",
  filename: "파일명",
  file: "파일",
};

// Pydantic 입력값 검사 에러 1개의 형식 (422 응답의 detail 배열 안의 항목)
interface ValidationIssue {
  type?: string;
  loc?: (string | number)[];
  msg?: string;
  ctx?: Record<string, unknown>;
}

// 백엔드 에러 응답 => 한국어 메시지
//  - 400/401/403/404 등: {"detail": "이미 존재하는 email입니다."} => 그대로 사용
//  - 422(입력값 오류): {"detail": [{type, loc, msg, ctx}, ...]} => 항목별로 한국어로 바꿈
function extractErrorMessage(payload: unknown, status: number): string {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (detail as ValidationIssue[]).map(translateIssue).join("\n");
  }
  return `요청 처리 중 오류가 발생했습니다. (HTTP ${status})`;
}

// 입력값 검사 에러 1개 => "비밀번호: 8자 이상 입력하세요." 같은 한국어 문장
function translateIssue(issue: ValidationIssue): string {
  const field = String(issue.loc?.[issue.loc.length - 1] ?? "");
  const label = FIELD_LABELS[field] ?? field;
  const ctx = issue.ctx ?? {};
  const messages: Record<string, string> = {
    missing: "필수 입력값입니다.",
    string_too_short: `${ctx.min_length}자 이상 입력하세요.`,
    string_too_long: `${ctx.max_length}자 이하로 입력하세요.`,
    value_error: "형식이 올바르지 않습니다. (예: 이메일 형식)",
    enum: "허용되지 않는 값입니다.",
    literal_error: "허용되지 않는 값입니다.",
    greater_than_equal: `${ctx.ge} 이상이어야 합니다.`,
    less_than_equal: `${ctx.le} 이하여야 합니다.`,
    int_parsing: "숫자를 입력하세요.",
    bool_parsing: "true 또는 false 여야 합니다.",
  };
  const message = (issue.type && messages[issue.type]) || issue.msg || "입력값이 올바르지 않습니다.";
  return label ? `${label}: ${message}` : message;
}
