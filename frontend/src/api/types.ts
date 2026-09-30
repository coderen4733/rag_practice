// [수정] 새 파일 추가 - 백엔드 API가 주고받는 데이터의 타입 정의
//  - 기존: 없음
//  - 변경: backend/src/services/.../schemas.py 의 요청/응답 형식을 TypeScript 타입으로 옮김
//    => 백엔드 스키마가 바뀌면 이 파일도 함께 바꿔야 함

// 모든 API 응답의 공통 형식 (backend/src/common/response.py 의 ResponseSchema)
export interface ApiResponse<T> {
  message: string;
  data: T | null;
}

// ───────────── 사용자 (iam/user) ─────────────
export type Role = "admin" | "manager" | "user";

// 사용자 정보 (UserReadRes)
export interface User {
  id: number;
  email: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// 사용자 생성/회원가입 응답 (UserCreateRes, SignUpRes) - updated_at 없음
export interface CreatedUser {
  id: number;
  email: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

// 페이지 단위 목록 응답의 공통 형식 (UserReadListRes, DocumentReadListRes)
export interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  total_pages: number;
}

// 사용자 목록 조회 조건 (UserReadListQuery)
export interface UserListQuery {
  is_active?: boolean;
  role?: Role;
  email?: string;
  sort_by?: "created_at" | "updated_at" | "email" | "id";
  order?: "asc" | "desc";
  page?: number;
  size?: number;
}

// ───────────── 인증 (iam/auth) ─────────────
// 로그인 응답 (SignInRes)
export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

// 비밀번호 변경 응답 (ChangePasswordRes)
export interface ChangePasswordResult {
  success: boolean;
  signed_out_sessions: number;
}

// ───────────── 문서 (rag/document) ─────────────
export type DocumentStatus = "processing" | "completed" | "failed";

// 문서 정보 (DocumentRes)
export interface DocumentItem {
  id: number;
  filename: string;
  file_extension: string;
  file_size: number;
  status: DocumentStatus;
  chunk_count: number;
  error_message: string | null;
  uploaded_by: number | null;
  created_at: string;
  updated_at: string;
}

// 문서 목록 조회 조건 (DocumentReadListQuery)
export interface DocumentListQuery {
  status?: DocumentStatus;
  filename?: string;
  order?: "asc" | "desc";
  page?: number;
  size?: number;
}

// 문서 삭제 응답 (DocumentDeleteRes)
export interface DocumentDeleteResult {
  success: boolean;
  id: number;
}
