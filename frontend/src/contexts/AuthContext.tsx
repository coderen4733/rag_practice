// [수정] 새 파일 추가 - 로그인 상태 관리
//  - 기존: 없음
//  - 변경: 로그인한 사용자 정보와 로그인/로그아웃 기능을 모든 화면에서 사용할 수 있게 함
//    - status: "loading"(확인 중) / "authenticated"(로그인됨) / "guest"(로그인 안 됨)
//    - notice: 로그인 화면에 보여줄 안내 (예: "비밀번호가 변경되었습니다. 다시 로그인해 주세요.")

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { signIn, signOut } from "../api/auth";
import { AUTH_EXPIRED_EVENT, tokenStorage } from "../api/client";
import type { User } from "../api/types";
import { getMe } from "../api/users";

type AuthStatus = "loading" | "authenticated" | "guest";

interface LogoutOptions {
  // true: 서버에 로그아웃 요청을 보내지 않음 (비밀번호 변경처럼 서버에서 이미 로그아웃된 경우)
  skipServer?: boolean;
  // 로그인 화면에 보여줄 안내 문구
  notice?: string;
}

interface AuthContextValue {
  user: User | null;
  status: AuthStatus;
  notice: string | null;
  isAdmin: boolean; // 관리자(admin)인지
  isStaff: boolean; // 관리자급(admin 또는 manager)인지
  login: (email: string, password: string) => Promise<void>;
  logout: (options?: LogoutOptions) => Promise<void>;
  reloadUser: () => Promise<void>;
  clearNotice: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [notice, setNotice] = useState<string | null>(null);

  // 내 정보 다시 불러오기 (권한이 바뀌었을 수 있으므로 필요할 때 호출)
  const reloadUser = useCallback(async () => {
    const me = await getMe();
    setUser(me);
    setStatus("authenticated");
  }, []);

  // 1. 처음 화면이 열릴 때: 저장된 토큰이 있으면 내 정보를 불러와서 로그인 상태 복원
  useEffect(() => {
    if (!tokenStorage.getAccess()) {
      setStatus("guest");
      return;
    }
    reloadUser().catch(() => {
      // 토큰이 만료되었고 재발급도 실패한 경우 => 로그인 화면으로
      tokenStorage.clear();
      setUser(null);
      setStatus("guest");
    });
  }, [reloadUser]);

  // 2. API 요청 중 "로그인 만료" 이벤트가 오면 로그아웃 상태로 전환 (api/client.ts 참고)
  useEffect(() => {
    const handleExpired = () => {
      setUser(null);
      setStatus("guest");
      setNotice("로그인이 만료되었습니다. 다시 로그인해 주세요.");
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpired);
    // 화면이 사라질 때 이벤트 듣기를 멈춤 (메모리 누수 방지)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpired);
  }, []);

  // 3. 로그인: 토큰 발급 -> 저장 -> 내 정보 불러오기
  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await signIn(email, password);
      tokenStorage.save(tokens.access_token, tokens.refresh_token);
      setNotice(null);
      await reloadUser();
    },
    [reloadUser],
  );

  // 4. 로그아웃: 서버의 리프레시 토큰 삭제(실패해도 진행) -> 저장된 토큰 삭제
  const logout = useCallback(async (options: LogoutOptions = {}) => {
    const refreshToken = tokenStorage.getRefresh();
    if (!options.skipServer && refreshToken) {
      await signOut(refreshToken).catch(() => undefined);
    }
    tokenStorage.clear();
    setUser(null);
    setStatus("guest");
    setNotice(options.notice ?? null);
  }, []);

  const clearNotice = useCallback(() => setNotice(null), []);

  // useMemo: 값이 실제로 바뀔 때만 새 객체를 만듦 (불필요한 다시 그리기 방지)
  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      notice,
      isAdmin: user?.role === "admin",
      isStaff: user?.role === "admin" || user?.role === "manager",
      login,
      logout,
      reloadUser,
      clearNotice,
    }),
    [user, status, notice, login, logout, reloadUser, clearNotice],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// 사용법: const { user, isStaff, logout } = useAuth();
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth는 AuthProvider 안에서만 사용할 수 있습니다.");
  return context;
}
