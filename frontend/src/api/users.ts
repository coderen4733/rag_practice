// 사용자(user) API 호출 함수
//  - 백엔드 /users/* API (내 정보, 목록, 관리자 생성, 활성화, 권한 변경)

import { request, unwrap } from "./client";
import type { ApiResponse, CreatedUser, PageResult, Role, User, UserListQuery } from "./types";

// 내 정보 조회 (GET /users/me) - 로그인한 사용자 누구나
export async function getMe(): Promise<User> {
  return unwrap(await request<ApiResponse<User>>("/users/me"));
}

// 사용자 목록 조회 (GET /users/) - admin, manager 전용
//  - ⚠️ 주소 끝의 "/"를 빼면 백엔드가 주소를 바꾸라는 응답(307)을 보내므로 꼭 붙임
export async function listUsers(query: UserListQuery = {}): Promise<PageResult<User>> {
  return unwrap(
    await request<ApiResponse<PageResult<User>>>("/users/", { query: { ...query } }),
  );
}

// 관리자 계정 생성 (POST /users/) - admin 전용, 생성 즉시 사용 가능(is_active=true)
export async function createUser(input: {
  email: string;
  password: string;
  password_confirm: string;
  role: Role;
}): Promise<CreatedUser> {
  return unwrap(
    await request<ApiResponse<CreatedUser>>("/users/", { method: "POST", body: input }),
  );
}

// 사용자 활성화/비활성화 (PATCH /users/{id}/active) - admin, manager 전용
export async function updateUserActive(userId: number, isActive: boolean): Promise<User> {
  return unwrap(
    await request<ApiResponse<User>>(`/users/${userId}/active`, {
      method: "PATCH",
      body: { is_active: isActive },
    }),
  );
}

// 권한 변경 (PATCH /users/{id}/role) - admin 전용
export async function updateUserRole(userId: number, role: Role): Promise<User> {
  return unwrap(
    await request<ApiResponse<User>>(`/users/${userId}/role`, {
      method: "PATCH",
      body: { role },
    }),
  );
}
