// 로그인 / 회원가입 화면
//  - 하나의 카드 안에서 "로그인"과 "회원가입" 탭을 전환
//    - 로그인: POST /auth/sign-in -> 토큰 저장 -> 대시보드로 이동
//    - 회원가입: POST /auth/sign-up -> 관리자 승인 대기 안내 -> 로그인 탭으로 전환

import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { LogIn, Moon, Sun, UserPlus } from "lucide-react";

import { signUp } from "../api/auth";
import { ApiError } from "../api/client";
import { Alert, Spinner } from "../components/ui/Feedback";
import { useAuth } from "../contexts/AuthContext";
import { useCopilot } from "../contexts/CopilotContext";
import { useTheme } from "../contexts/ThemeContext";

type Tab = "login" | "signup";

// 에러 객체 => 화면에 보여줄 메시지
const errorMessage = (error: unknown) =>
  error instanceof ApiError ? error.message : "알 수 없는 오류가 발생했습니다.";

export function AuthPage() {
  const { login, notice, clearNotice } = useAuth();
  const { pushMessage } = useCopilot();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();

  const [tab, setTab] = useState<Tab>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false); // 요청 중이면 버튼 비활성화
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 로그인 전에 가려던 주소 (예: /documents) - 로그인 후 그 주소로 보내줌
  const redirectTo = (location.state as { from?: string } | null)?.from ?? "/";

  // 탭 전환 시 메시지 초기화
  const changeTab = (next: Tab) => {
    setTab(next);
    setError(null);
    setSuccess(null);
    clearNotice();
  };

  // 로그인
  const handleLogin = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
      pushMessage({ sender: "ai", tone: "success", text: `${email.trim()} 계정으로 로그인했습니다.` });
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  // 회원가입
  const handleSignUp = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    // 서버에 보내기 전에 화면에서 먼저 확인 (서버도 한 번 더 확인함)
    if (password !== passwordConfirm) {
      setError("비밀번호가 서로 일치하지 않습니다.");
      return;
    }
    setSubmitting(true);
    try {
      const { message } = await signUp(email.trim(), password, passwordConfirm);
      setPassword("");
      setPasswordConfirm("");
      setTab("login");
      setSuccess(message); // "회원가입에 성공했습니다. 관리자 승인 후 로그인할 수 있습니다."
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page">
      {/* 오른쪽 위 테마 전환 버튼 */}
      <div className="auth-top-actions">
        <button type="button" className="icon-button" onClick={toggleTheme} aria-label="테마 전환">
          {theme === "light" ? <Moon size={19} /> : <Sun size={19} />}
        </button>
      </div>

      <div className="auth-card">
        <div className="brand">
          ONGYEOL <span className="brand-mark">AI</span>
        </div>
        <p className="muted" style={{ textAlign: "center", marginBottom: 22 }}>
          사내 지식베이스 · RAG 테스트 콘솔
        </p>

        {/* 로그인 / 회원가입 탭 */}
        <div className="segmented" style={{ display: "flex", marginBottom: 18 }}>
          <button type="button" className={tab === "login" ? "active" : ""} style={{ flex: 1, justifyContent: "center" }} onClick={() => changeTab("login")}>
            <LogIn size={15} /> 로그인
          </button>
          <button type="button" className={tab === "signup" ? "active" : ""} style={{ flex: 1, justifyContent: "center" }} onClick={() => changeTab("signup")}>
            <UserPlus size={15} /> 회원가입
          </button>
        </div>

        <div className="form-stack">
          {notice && <Alert tone="info">{notice}</Alert>}
          {success && <Alert tone="success">{success}</Alert>}
          {error && <Alert tone="error">{error}</Alert>}

          <form className="form-stack" onSubmit={tab === "login" ? handleLogin : handleSignUp}>
            <div className="field">
              <label htmlFor="email">이메일</label>
              <input
                id="email"
                className="input"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@company.com"
                required
              />
            </div>
            <div className="field">
              <label htmlFor="password">비밀번호</label>
              <input
                id="password"
                className="input"
                type="password"
                autoComplete={tab === "login" ? "current-password" : "new-password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="8자 이상"
                required
              />
            </div>
            {tab === "signup" && (
              <div className="field">
                <label htmlFor="password-confirm">비밀번호 확인</label>
                <input
                  id="password-confirm"
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  value={passwordConfirm}
                  onChange={(event) => setPasswordConfirm(event.target.value)}
                  required
                />
                <span className="hint">가입 후 관리자가 승인해야 로그인할 수 있습니다.</span>
              </div>
            )}
            <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
              {submitting && <Spinner size={15} />}
              {tab === "login" ? "로그인" : "회원가입"}
            </button>
          </form>

          {/* 개발/테스트용 안내: 처음에는 관리자가 없으므로 DB에서 직접 지정해야 함 */}
          <details className="muted" style={{ fontSize: 12 }}>
            <summary style={{ cursor: "pointer" }}>처음 관리자 계정은 어떻게 만드나요?</summary>
            <p style={{ marginTop: 8, lineHeight: 1.6 }}>
              1) 회원가입 → 2) Supabase SQL Editor에서 아래 실행 → 3) 로그인
              <br />
              <code className="mono">
                UPDATE rag_practice.users SET role = &apos;admin&apos;, is_active = true WHERE email = &apos;가입한
                이메일&apos;;
              </code>
            </p>
          </details>
        </div>
      </div>
    </div>
  );
}
