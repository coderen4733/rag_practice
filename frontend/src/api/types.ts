//  * 백엔드 API가 주고받는 데이터의 타입 정의
//  - backend/src/services/.../schemas.py 의 요청/응답 형식을 TypeScript 타입으로 옮김
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

// ───────────── 문서 검색 (rag/search) 타입 ─────────────
//  - POST /search/ 의 요청(SearchReq)과 응답(SearchRes) 형식

// 문서 검색 요청 (SearchReq)
export interface SearchRequest {
  query: string;
  top_k?: number; // 가져올 결과 수 (1~20, 기본 5)
  document_ids?: number[]; // 특정 문서에서만 검색 (생략하면 전체)
}

// 검색 결과 1개 (SearchHitRes)
export interface SearchHit {
  rank: number;
  document_id: number;
  filename: string;
  chunk_index: number;
  text: string;
  score: number; // 유사도 (1에 가까울수록 비슷함)
}

// ───────────── 챗봇 (rag/chat) 타입 ─────────────
//  - POST /chat/stream, GET /chat/status 의 요청/응답 형식

// 챗봇 질문 (ChatReq)
export interface ChatRequest {
  question: string;
  top_k?: number; // 근거로 쓸 청크 수 (생략하면 서버 설정값)
  document_ids?: number[];
  // 이어서 질문할 대화방 id (생략하면 새 대화방을 만듦)
  conversation_id?: number;
}

//  * 스트리밍 답변 끝(done 이벤트) 정보
//  - 대화방 정보와 검색에 사용한 질문을 함께 받음
//    => 다음 질문 때 conversation_id를 보내면 대화가 이어짐
export interface ChatDoneInfo {
  model: string;
  elapsed_ms: number;
  conversation_id: number; // 질문/답변이 저장된 대화방 id
  conversation_title: string; // 대화방 제목
  search_query: string; // 검색에 사용한 질문 (이어서 묻는 질문이면 LLM이 다시 쓴 질문)
}

// 답변의 근거(출처) 1개 (ChatSourceRes) - number는 답변 안의 [1], [2]와 연결됨
export interface ChatSource {
  number: number;
  document_id: number;
  filename: string;
  chunk_index: number;
  text: string;
  score: number;
}

// 대화방 1개 (ConversationRes) - 대화방 목록에서 사용
export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string; // 마지막으로 대화한 시각 (목록 정렬 기준)
}

// 저장된 대화 메시지 1개 (ChatMessageRes)
export interface ConversationMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  search_query: string | null; // 검색에 사용한 질문 (질문 메시지만)
  sources: ChatSource[] | null; // 근거 문서 (답변 메시지만)
  model: string | null; // 답변을 만든 LLM 모델 (답변 메시지만)
  created_at: string;
}

// 대화방 열기 응답 (ConversationDetailRes) - 대화방 정보 + 메시지 전체 (오래된 순)
export interface ConversationDetail extends Conversation {
  messages: ConversationMessage[];
}

// 대화방 삭제 결과 (ConversationDeleteRes)
export interface ConversationDeleteResult {
  success: boolean;
  id: number;
}

// LLM 연결 상태 (ChatStatusRes)
export interface ChatStatus {
  model: string;
  available: boolean;
  message: string | null;
}

// 문서 검색 응답 (SearchRes)
export interface SearchResult {
  query: string;
  top_k: number;
  total: number;
  elapsed_ms: number;
  results: SearchHit[];
}
