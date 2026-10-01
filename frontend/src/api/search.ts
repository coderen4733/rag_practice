//  * 문서 검색(search) API 호출 함수
//  - 백엔드 POST /search/ (질문과 의미가 비슷한 문서 청크 찾기)

import { request, unwrap } from "./client";
import type { ApiResponse, SearchRequest, SearchResult } from "./types";

// 문서 검색 (POST /search/) - 로그인한 사용자 누구나
//  - ⚠️ 주소 끝의 "/"를 빼면 백엔드가 주소를 바꾸라는 응답(307)을 보내므로 꼭 붙임
export async function searchDocuments(input: SearchRequest): Promise<SearchResult> {
  return unwrap(
    await request<ApiResponse<SearchResult>>("/search/", { method: "POST", body: input }),
  );
}
