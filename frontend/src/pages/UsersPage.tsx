// [수정] 새 파일 추가 - 사용자·권한 관리 화면 (admin, manager 전용)
//  - 기존: 없음
//  - 변경: 사용자 목록 조회 + 승인/비활성화 + 권한 변경 + 사용자 생성
//    - 목록: 승인 상태 탭, 권한/이메일 필터, 정렬, 페이지 번호 (GET /users/)
//    - 승인/비활성화: admin, manager (PATCH /users/{id}/active)
//        * manager는 일반 사용자(user) 계정만 변경 가능, 자기 자신은 변경 불가 (백엔드 규칙과 동일)
//    - 권한 변경: admin 전용 (PATCH /users/{id}/role), 자기 자신은 변경 불가
//    - 사용자 생성: admin 전용 (POST /users/), 생성 즉시 사용 가능
//  - 주소에 ?is_active=false 가 있으면 "승인 대기" 탭으로 시작 (헤더 알림 버튼에서 이동할 때)

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { RefreshCw, Search, UserPlus, Users } from "lucide-react";

import { ApiError } from "../api/client";
import type { PageResult, Role, User, UserListQuery } from "../api/types";
import { createUser, listUsers, updateUserActive, updateUserRole } from "../api/users";
import { Badge } from "../components/ui/Badge";
import { Alert, EmptyState, Spinner } from "../components/ui/Feedback";
import { Modal } from "../components/ui/Modal";
import { Pagination } from "../components/ui/Pagination";
import { useAuth } from "../contexts/AuthContext";
import { useCopilot } from "../contexts/CopilotContext";
import { ROLE_LABELS, formatDateTime, formatNumber } from "../utils/format";

const ROLES: Role[] = ["admin", "manager", "user"];

// 권한별 배지 색상
const ROLE_TONES = { admin: "brand", manager: "info", user: "neutral" } as const;

const errorMessage = (error: unknown) =>
  error instanceof ApiError ? error.message : "알 수 없는 오류가 발생했습니다.";

// 주소의 ?is_active=true/false 값을 읽어서 필터 값으로 바꿈
function parseActiveParam(value: string | null): boolean | undefined {
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

export function UsersPage() {
  const { user: me, isAdmin } = useAuth();
  const { pushMessage } = useCopilot();
  const [searchParams, setSearchParams] = useSearchParams();

  // ───────────── 1. 목록 상태 ─────────────
  const [query, setQuery] = useState<UserListQuery>(() => ({
    is_active: parseActiveParam(searchParams.get("is_active")),
    sort_by: "created_at",
    order: "desc",
    page: 1,
    size: 10,
  }));
  const [emailInput, setEmailInput] = useState("");
  const [result, setResult] = useState<PageResult<User> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null); // 작업 성공 안내
  const [pendingCount, setPendingCount] = useState<number | null>(null); // 승인 대기 수 (탭에 표시)
  const [busyUserId, setBusyUserId] = useState<number | null>(null); // 작업 중인 사용자 (버튼 비활성화용)

  // ───────────── 2. 사용자 생성 팝업 상태 ─────────────
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ email: "", password: "", password_confirm: "", role: "user" as Role });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // 주소의 ?is_active 값이 바뀌면 (예: 헤더 알림 버튼) 필터에 반영
  useEffect(() => {
    const isActive = parseActiveParam(searchParams.get("is_active"));
    setQuery((current) => (current.is_active === isActive ? current : { ...current, is_active: isActive, page: 1 }));
  }, [searchParams]);

  // 목록 + 승인 대기 수 불러오기
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, pending] = await Promise.all([listUsers(query), listUsers({ is_active: false, size: 1 })]);
      setResult(list);
      setPendingCount(pending.total);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    load();
  }, [load]);

  // 조건 바꾸기 (조건이 바뀌면 1페이지부터)
  const updateQuery = (patch: Partial<UserListQuery>) => setQuery((current) => ({ ...current, page: 1, ...patch }));

  // 승인 상태 탭 바꾸기 (주소의 ?is_active 도 함께 바꿔서 새로고침해도 유지)
  const changeActiveTab = (isActive: boolean | undefined) => {
    setSearchParams(isActive === undefined ? {} : { is_active: String(isActive) });
    updateQuery({ is_active: isActive });
  };

  // ───────────── 3. 버튼을 누를 수 없는 이유 (백엔드 규칙과 동일) ─────────────
  const activeBlockReason = (target: User): string | null => {
    if (!me) return "로그인이 필요합니다.";
    if (target.id === me.id) return "자기 자신의 계정은 변경할 수 없습니다.";
    if (me.role === "manager" && target.role !== "user") return "매니저는 일반 사용자 계정만 변경할 수 있습니다.";
    return null;
  };

  // ───────────── 4. 승인 / 비활성화 ─────────────
  const toggleActive = async (target: User) => {
    setBusyUserId(target.id);
    setError(null);
    setNotice(null);
    try {
      const updated = await updateUserActive(target.id, !target.is_active);
      const action = updated.is_active ? "승인(활성화)" : "비활성화";
      setNotice(`${updated.email} 계정을 ${action}했습니다.`);
      pushMessage({ sender: "ai", tone: "success", text: `${updated.email} 계정을 ${action}했습니다.` });
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyUserId(null);
    }
  };

  // ───────────── 5. 권한 변경 (admin 전용) ─────────────
  const changeRole = async (target: User, role: Role) => {
    if (role === target.role) return;
    setBusyUserId(target.id);
    setError(null);
    setNotice(null);
    try {
      const updated = await updateUserRole(target.id, role);
      setNotice(`${updated.email} 계정의 권한을 ${ROLE_LABELS[updated.role]}(으)로 변경했습니다.`);
      pushMessage({
        sender: "ai",
        tone: "success",
        text: `${updated.email} 권한 변경: ${ROLE_LABELS[target.role]} → ${ROLE_LABELS[updated.role]}`,
      });
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyUserId(null);
    }
  };

  // ───────────── 6. 사용자 생성 (admin 전용) ─────────────
  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    setCreateError(null);
    if (createForm.password !== createForm.password_confirm) {
      setCreateError("비밀번호가 서로 일치하지 않습니다.");
      return;
    }
    setCreating(true);
    try {
      const created = await createUser({ ...createForm, email: createForm.email.trim() });
      setCreateOpen(false);
      setCreateForm({ email: "", password: "", password_confirm: "", role: "user" });
      setNotice(`${created.email} 계정을 ${ROLE_LABELS[created.role]} 권한으로 생성했습니다. (바로 로그인 가능)`);
      pushMessage({ sender: "ai", tone: "success", text: `${created.email} 계정을 생성했습니다.` });
      await load();
    } catch (err) {
      setCreateError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const handleSearch = (event: FormEvent) => {
    event.preventDefault();
    updateQuery({ email: emailInput.trim() || undefined });
  };

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-row">
          <h1 className="page-title">사용자·권한 관리</h1>
          <p className="page-desc">회원가입한 계정을 승인하고, 권한을 관리합니다.</p>
        </div>
        {isAdmin && (
          <button type="button" className="btn btn-primary" onClick={() => setCreateOpen(true)}>
            <UserPlus size={15} /> 사용자 생성
          </button>
        )}
      </div>

      <div className="stack">
        {notice && <Alert tone="success">{notice}</Alert>}
        {error && <Alert tone="error">{error}</Alert>}
        {!isAdmin && <Alert tone="info">매니저 권한은 일반 사용자 계정의 승인·비활성화만 할 수 있습니다. 권한 변경과 사용자 생성은 관리자만 가능합니다.</Alert>}

        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Users size={17} /> 사용자 목록 <span className="count-pill">{result ? formatNumber(result.total) : "-"}</span>
            </div>
            <button type="button" className="btn btn-outline btn-sm" onClick={load} disabled={loading}>
              {loading ? <Spinner size={14} /> : <RefreshCw size={14} />} 새로고침
            </button>
          </div>

          {/* 필터 */}
          <div className="filters">
            <div className="segmented">
              <button type="button" className={query.is_active === undefined ? "active" : ""} onClick={() => changeActiveTab(undefined)}>
                전체
              </button>
              <button type="button" className={query.is_active === true ? "active" : ""} onClick={() => changeActiveTab(true)}>
                승인됨
              </button>
              <button type="button" className={query.is_active === false ? "active" : ""} onClick={() => changeActiveTab(false)}>
                승인 대기
                {pendingCount !== null && pendingCount > 0 && <Badge tone="brand">{pendingCount}</Badge>}
              </button>
            </div>
            <select
              className="select"
              value={query.role ?? ""}
              onChange={(event) => updateQuery({ role: (event.target.value || undefined) as Role | undefined })}
              aria-label="권한 필터"
            >
              <option value="">모든 권한</option>
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {ROLE_LABELS[role]}
                </option>
              ))}
            </select>
            <form onSubmit={handleSearch} style={{ display: "flex", gap: 6 }}>
              <input
                className="input"
                value={emailInput}
                onChange={(event) => setEmailInput(event.target.value)}
                placeholder="이메일 검색"
                aria-label="이메일 검색"
              />
              <button type="submit" className="btn btn-outline">
                <Search size={15} /> 검색
              </button>
            </form>
            <select
              className="select"
              value={`${query.sort_by}:${query.order}`}
              onChange={(event) => {
                const [sortBy, order] = event.target.value.split(":");
                updateQuery({ sort_by: sortBy as UserListQuery["sort_by"], order: order as "asc" | "desc" });
              }}
              aria-label="정렬"
            >
              <option value="created_at:desc">최신 가입순</option>
              <option value="created_at:asc">오래된 가입순</option>
              <option value="updated_at:desc">최근 수정순</option>
              <option value="email:asc">이메일 가나다순</option>
            </select>
          </div>

          {result && result.items.length > 0 ? (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="center">ID</th>
                      <th>이메일</th>
                      <th className="center">권한</th>
                      <th className="center">상태</th>
                      <th>가입일</th>
                      <th>수정일</th>
                      <th className="right">작업</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.items.map((target) => {
                      const blockReason = activeBlockReason(target);
                      const isMe = target.id === me?.id;
                      const busy = busyUserId === target.id;
                      return (
                        <tr key={target.id}>
                          <td className="center muted">{target.id}</td>
                          <td style={{ fontWeight: 600 }}>
                            {target.email} {isMe && <Badge tone="info">나</Badge>}
                          </td>
                          <td className="center">
                            <Badge tone={ROLE_TONES[target.role]}>{ROLE_LABELS[target.role]}</Badge>
                          </td>
                          <td className="center">
                            {target.is_active ? <Badge tone="success">승인됨</Badge> : <Badge tone="warning">승인 대기</Badge>}
                          </td>
                          <td className="muted">{formatDateTime(target.created_at)}</td>
                          <td className="muted">{formatDateTime(target.updated_at)}</td>
                          <td>
                            <div className="cell-actions">
                              {/* 권한 변경 (admin만, 자기 자신 제외) */}
                              {isAdmin && (
                                <select
                                  className="select"
                                  style={{ height: 30, fontSize: 12.5 }}
                                  value={target.role}
                                  disabled={isMe || busy}
                                  title={isMe ? "자기 자신의 권한은 변경할 수 없습니다." : "권한 변경"}
                                  onChange={(event) => changeRole(target, event.target.value as Role)}
                                  aria-label={`${target.email} 권한 변경`}
                                >
                                  {ROLES.map((role) => (
                                    <option key={role} value={role}>
                                      {ROLE_LABELS[role]}
                                    </option>
                                  ))}
                                </select>
                              )}
                              {/* 승인 / 비활성화 */}
                              <button
                                type="button"
                                className={`btn btn-sm ${target.is_active ? "btn-danger-outline" : "btn-primary"}`}
                                disabled={blockReason !== null || busy}
                                title={blockReason ?? undefined}
                                onClick={() => toggleActive(target)}
                              >
                                {busy && <Spinner size={13} />}
                                {target.is_active ? "비활성화" : "승인"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={result.page}
                totalPages={result.total_pages}
                total={result.total}
                onChange={(page) => setQuery((current) => ({ ...current, page }))}
              />
            </>
          ) : (
            <EmptyState
              icon={loading ? <Spinner size={22} /> : <Users size={26} />}
              title={loading ? "불러오는 중..." : "조건에 맞는 사용자가 없습니다."}
            />
          )}
        </div>
      </div>

      {/* 사용자 생성 팝업 (admin 전용) */}
      {createOpen && (
        <Modal title="사용자 생성" onClose={() => setCreateOpen(false)}>
          <form className="form-stack" onSubmit={handleCreate}>
            <Alert tone="info">관리자가 만든 계정은 승인 없이 바로 로그인할 수 있습니다.</Alert>
            {createError && <Alert tone="error">{createError}</Alert>}
            <div className="field">
              <label htmlFor="new-email">이메일</label>
              <input
                id="new-email"
                className="input"
                type="email"
                value={createForm.email}
                onChange={(event) => setCreateForm({ ...createForm, email: event.target.value })}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="new-password">비밀번호</label>
              <input
                id="new-password"
                className="input"
                type="password"
                autoComplete="new-password"
                value={createForm.password}
                onChange={(event) => setCreateForm({ ...createForm, password: event.target.value })}
                placeholder="8자 이상"
                required
              />
            </div>
            <div className="field">
              <label htmlFor="new-password-confirm">비밀번호 확인</label>
              <input
                id="new-password-confirm"
                className="input"
                type="password"
                autoComplete="new-password"
                value={createForm.password_confirm}
                onChange={(event) => setCreateForm({ ...createForm, password_confirm: event.target.value })}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="new-role">권한</label>
              <select
                id="new-role"
                className="select"
                value={createForm.role}
                onChange={(event) => setCreateForm({ ...createForm, role: event.target.value as Role })}
              >
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABELS[role]}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button type="button" className="btn btn-outline" onClick={() => setCreateOpen(false)}>
                취소
              </button>
              <button type="submit" className="btn btn-primary" disabled={creating}>
                {creating && <Spinner size={14} />} 생성
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
