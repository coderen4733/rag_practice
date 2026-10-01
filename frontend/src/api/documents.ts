//  * 문서(document) API 호출 함수
//  - 백엔드 /documents/* API (업로드, 목록, 상세, 삭제)

import { request, unwrap } from "./client";
import type {
  ApiResponse,
  DocumentDeleteResult,
  DocumentItem,
  DocumentListQuery,
  PageResult,
} from "./types";

// 문서 업로드 (POST /documents/) - admin, manager 전용
//  - 파일은 JSON이 아니라 FormData(multipart/form-data) 형식으로 보냄
//  - 백엔드는 업로드 요청 안에서 청크 분할 -> 임베딩 -> Qdrant 저장까지 끝낸 뒤 응답함
//    => 문서가 크면 응답까지 시간이 걸릴 수 있음
export async function uploadDocument(file: File): Promise<DocumentItem> {
  const form = new FormData();
  form.append("file", file); // "file": 백엔드 router의 매개변수 이름과 같아야 함
  return unwrap(
    await request<ApiResponse<DocumentItem>>("/documents/", { method: "POST", form }),
  );
}

// 문서 목록 조회 (GET /documents/) - 로그인한 사용자 누구나
export async function listDocuments(
  query: DocumentListQuery = {},
): Promise<PageResult<DocumentItem>> {
  return unwrap(
    await request<ApiResponse<PageResult<DocumentItem>>>("/documents/", {
      query: { ...query },
    }),
  );
}

// 문서 상세 조회 (GET /documents/{id}) - 로그인한 사용자 누구나
export async function getDocument(documentId: number): Promise<DocumentItem> {
  return unwrap(await request<ApiResponse<DocumentItem>>(`/documents/${documentId}`));
}

// 문서 삭제 (DELETE /documents/{id}) - admin, manager 전용 (Qdrant 청크도 함께 삭제)
export async function deleteDocument(documentId: number): Promise<DocumentDeleteResult> {
  return unwrap(
    await request<ApiResponse<DocumentDeleteResult>>(`/documents/${documentId}`, {
      method: "DELETE",
    }),
  );
}
