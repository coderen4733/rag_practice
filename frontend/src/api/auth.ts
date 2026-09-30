// [수정] 새 파일 추가 - 인증(auth) API 호출 함수
//  - 기존: 없음
//  - 변경: 백엔드 /auth/* API (회원가입, 로그인, 로그아웃, 비밀번호 변경)

import { request, unwrap } from "./client";
import type { ApiResponse, ChangePasswordResult, CreatedUser, TokenPair } from "./types";

// 회원가입 (POST /auth/sign-up) - 로그인 없이 호출
//  - 가입한 계정은 관리자 승인 전까지 로그인할 수 없음 (is_active=false)
export async function signUp(email: string, password: string, passwordConfirm: string) {
  const response = await request<ApiResponse<CreatedUser>>("/auth/sign-up", {
    method: "POST",
    auth: false,
    body: { email, password, password_confirm: passwordConfirm },
  });
  return { message: response.message, user: unwrap(response) };
}

// 로그인 (POST /auth/sign-in) - 액세스 토큰 + 리프레시 토큰을 돌려받음
export async function signIn(email: string, password: string): Promise<TokenPair> {
  const response = await request<ApiResponse<TokenPair>>("/auth/sign-in", {
    method: "POST",
    auth: false,
    body: { email, password },
  });
  return unwrap(response);
}

// 로그아웃 (POST /auth/sign-out) - 서버에 저장된 리프레시 토큰을 삭제
export async function signOut(refreshToken: string): Promise<void> {
  await request<ApiResponse<{ success: boolean }>>("/auth/sign-out", {
    method: "POST",
    auth: false,
    body: { refresh_token: refreshToken },
  });
}

// 비밀번호 변경 (PATCH /auth/password) - 성공하면 모든 기기에서 로그아웃됨
export async function changePassword(
  currentPassword: string,
  newPassword: string,
  newPasswordConfirm: string,
) {
  const response = await request<ApiResponse<ChangePasswordResult>>("/auth/password", {
    method: "PATCH",
    body: {
      current_password: currentPassword,
      new_password: newPassword,
      new_password_confirm: newPasswordConfirm,
    },
  });
  return { message: response.message, result: unwrap(response) };
}
