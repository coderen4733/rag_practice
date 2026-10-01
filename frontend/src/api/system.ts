// 시스템 상태 API 호출 함수
//  - 백엔드 /health-check (서버가 살아 있는지 확인)

import { request } from "./client";

// 서버 상태 확인 (GET /health-check) - 응답 형식: {"status": "healthy"}
//  - ResponseSchema(message + data) 형식이 아니라서 unwrap을 쓰지 않음
export async function healthCheck(): Promise<{ status: string }> {
  return request<{ status: string }>("/health-check", { auth: false });
}
