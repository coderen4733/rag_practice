//  * 내 계정 화면
//  - 내 정보 조회(GET /users/me) + 비밀번호 변경(PATCH /auth/password) + 로그아웃
//    - 비밀번호를 바꾸면 서버가 모든 기기의 로그인을 끊으므로, 이 화면도 로그인 화면으로 이동함

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { KeyRound, LogOut, RefreshCw, UserRound } from "lucide-react";

import { changePassword } from "../api/auth";
import { ApiError } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Alert, Spinner } from "../components/ui/Feedback";
import { useAuth } from "../contexts/AuthContext";
import { ROLE_LABELS, formatDateTime } from "../utils/format";

const errorMessage = (error: unknown) =>
  error instanceof ApiError ? error.message : "알 수 없는 오류가 발생했습니다.";

export function AccountPage() {
  const { user, logout, reloadUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const passwordCardRef = useRef<HTMLDivElement>(null);

  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);

  // 주소가 /account#password 이면 비밀번호 변경 카드로 스크롤 (헤더 메뉴에서 이동할 때)
  useEffect(() => {
    if (location.hash === "#password") {
      passwordCardRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [location.hash]);

  // 내 정보 새로고침 (관리자가 권한을 바꿨을 수 있으므로)
  const handleReload = async () => {
    setReloading(true);
    await reloadUser().catch(() => undefined);
    setReloading(false);
  };

  // 비밀번호 변경
  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (form.next !== form.confirm) {
      setError("새 비밀번호가 서로 일치하지 않습니다.");
      return;
    }
    setSubmitting(true);
    try {
      const { result } = await changePassword(form.current, form.next, form.confirm);
      // 서버에서 이미 모든 기기가 로그아웃되었으므로 서버 요청 없이 로그아웃 처리
      await logout({
        skipServer: true,
        notice: `비밀번호가 변경되었습니다. ${result.signed_out_sessions}개 기기에서 로그아웃되었으니 새 비밀번호로 다시 로그인해 주세요.`,
      });
      navigate("/login", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
      setSubmitting(false);
    }
  };

  const handleLogout = async () => {
    await logout({ notice: "로그아웃되었습니다." });
    navigate("/login", { replace: true });
  };

  if (!user) return null;

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-row">
          <h1 className="page-title">내 계정</h1>
          <p className="page-desc">내 정보를 확인하고 비밀번호를 변경합니다.</p>
        </div>
        <button type="button" className="btn btn-outline" onClick={handleLogout}>
          <LogOut size={15} /> 로그아웃
        </button>
      </div>

      <div className="grid-2">
        {/* 1. 내 정보 */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <UserRound size={17} /> 내 정보
            </div>
            <button type="button" className="btn btn-outline btn-sm" onClick={handleReload} disabled={reloading}>
              {reloading ? <Spinner size={14} /> : <RefreshCw size={14} />} 새로고침
            </button>
          </div>
          <div className="card-body">
            <dl className="detail-list">
              <dt>사용자 ID</dt>
              <dd>{user.id}</dd>
              <dt>이메일</dt>
              <dd>{user.email}</dd>
              <dt>권한</dt>
              <dd>
                <Badge tone="brand">{ROLE_LABELS[user.role]}</Badge>
              </dd>
              <dt>상태</dt>
              <dd>{user.is_active ? <Badge tone="success">승인됨</Badge> : <Badge tone="warning">승인 대기</Badge>}</dd>
              <dt>가입일</dt>
              <dd>{formatDateTime(user.created_at)}</dd>
              <dt>수정일</dt>
              <dd>{formatDateTime(user.updated_at)}</dd>
            </dl>
          </div>
        </div>

        {/* 2. 비밀번호 변경 */}
        <div className="card" id="password" ref={passwordCardRef}>
          <div className="card-header">
            <div className="card-title">
              <KeyRound size={17} /> 비밀번호 변경
            </div>
          </div>
          <form className="card-body form-stack" onSubmit={handleSubmit}>
            <Alert tone="warning">비밀번호를 변경하면 이 기기를 포함한 모든 기기에서 로그아웃됩니다.</Alert>
            {error && <Alert tone="error">{error}</Alert>}
            <div className="field">
              <label htmlFor="current-password">현재 비밀번호</label>
              <input
                id="current-password"
                className="input"
                type="password"
                autoComplete="current-password"
                value={form.current}
                onChange={(event) => setForm({ ...form, current: event.target.value })}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="next-password">새 비밀번호</label>
              <input
                id="next-password"
                className="input"
                type="password"
                autoComplete="new-password"
                value={form.next}
                onChange={(event) => setForm({ ...form, next: event.target.value })}
                placeholder="8자 이상, 현재 비밀번호와 달라야 함"
                required
              />
            </div>
            <div className="field">
              <label htmlFor="confirm-password">새 비밀번호 확인</label>
              <input
                id="confirm-password"
                className="input"
                type="password"
                autoComplete="new-password"
                value={form.confirm}
                onChange={(event) => setForm({ ...form, confirm: event.target.value })}
                required
              />
            </div>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting && <Spinner size={14} />} 비밀번호 변경
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
