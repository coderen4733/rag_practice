//  * 대시보드 (로그인 후 첫 화면)
//  - 문서 수, 처리 상태, 승인 대기 사용자 수, 최근 문서, 서버 상태, RAG 진행 단계를 한눈에 보여줌
//    - 여러 API를 동시에 호출하고(Promise.allSettled), 일부가 실패해도 나머지는 표시함

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  CircleCheck,
  CircleX,
  FileText,
  RefreshCw,
  Server,
  ShieldCheck,
  UserPlus,
  Workflow,
} from "lucide-react";

import { listDocuments } from "../api/documents";
import { healthCheck } from "../api/system";
import type { DocumentItem } from "../api/types";
import { listUsers } from "../api/users";
import { Badge } from "../components/ui/Badge";
import { EmptyState, Spinner } from "../components/ui/Feedback";
import { useAuth } from "../contexts/AuthContext";
import { DOCUMENT_STATUS, ROLE_LABELS, displayName, formatBytes, formatDateTime, formatNumber } from "../utils/format";

// 대시보드에 보여줄 숫자들 (null: 불러오지 못함)
interface DashboardStats {
  documents: number | null;
  completed: number | null;
  failed: number | null;
  pendingUsers: number | null;
  recent: DocumentItem[];
  healthy: boolean | null;
}

// RAG 기능 진행 단계 (프로젝트 로드맵)
const ROADMAP = [
  { label: "① 계정·권한 관리", done: true },
  { label: "② 문서 등록 (청크 분할 · 임베딩 · Vector DB 저장)", done: true },
  // ③ 문서 검색 완료 표시 (기존: done: false)
  { label: "③ 문서 검색 (유사도 검색)", done: true },
  // ④ 챗봇을 두 단계로 나눠 표시 (기존: "④ 챗봇 (문서 근거 답변)" 하나, 준비중)
  { label: "④-1 챗봇 (문서 근거 답변 · 스트리밍)", done: true },
  { label: "④-2 대화 이어가기 · 대화 이력", done: false },
  { label: "⑤ AI 에이전트", done: false },
];

// 통계 카드 1개
function StatCard({
  icon,
  color,
  value,
  label,
  to,
}: {
  icon: ReactNode;
  color: string; // 아이콘 배경색 (CSS 변수 이름, 예: "info")
  value: string;
  label: string;
  to?: string; // 누르면 이동할 주소
}) {
  const content = (
    <div className="stat-card" style={to ? { cursor: "pointer" } : undefined}>
      <div className="stat-top">
        <span className="stat-icon" style={{ background: `var(--${color}-soft)`, color: `var(--${color})` }}>
          {icon}
        </span>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
  return to ? <Link to={to}>{content}</Link> : content;
}

export function DashboardPage() {
  const { user, isStaff } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  // 여러 API를 동시에 호출해서 대시보드 숫자 채우기
  const load = useCallback(async () => {
    setLoading(true);
    // allSettled: 하나가 실패해도 나머지 결과를 모두 받음 (all은 하나만 실패해도 전체 실패)
    const [all, completed, failed, pending, health] = await Promise.allSettled([
      listDocuments({ size: 5 }),
      listDocuments({ status: "completed", size: 1 }),
      listDocuments({ status: "failed", size: 1 }),
      // 승인 대기 사용자 수는 관리자급만 조회 가능
      isStaff ? listUsers({ is_active: false, size: 1 }) : Promise.reject(new Error("권한 없음")),
      healthCheck(),
    ]);
    setStats({
      documents: all.status === "fulfilled" ? all.value.total : null,
      recent: all.status === "fulfilled" ? all.value.items : [],
      completed: completed.status === "fulfilled" ? completed.value.total : null,
      failed: failed.status === "fulfilled" ? failed.value.total : null,
      pendingUsers: pending.status === "fulfilled" ? pending.value.total : null,
      healthy: health.status === "fulfilled" ? health.value.status === "healthy" : false,
    });
    setLoading(false);
  }, [isStaff]);

  useEffect(() => {
    load();
  }, [load]);

  // 숫자 표시 (불러오지 못했으면 "-")
  const show = (value: number | null | undefined) => (value === null || value === undefined ? "-" : formatNumber(value));

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title" style={{ fontSize: 24 }}>
            안녕하세요, {user ? displayName(user.email) : ""}님
          </h1>
          <p className="page-desc" style={{ marginTop: 6 }}>
            사내 지식베이스의 문서 등록 현황과 시스템 상태를 한눈에 확인합니다.
          </p>
        </div>
        <button type="button" className="btn btn-outline" onClick={load} disabled={loading}>
          {loading ? <Spinner size={15} /> : <RefreshCw size={15} />} 새로고침
        </button>
      </div>

      <div className="stack">
        {/* 1. 통계 카드 */}
        <div className="stat-grid">
          <StatCard icon={<FileText size={20} />} color="info" value={show(stats?.documents)} label="등록 문서" to="/documents" />
          <StatCard icon={<CircleCheck size={20} />} color="success" value={show(stats?.completed)} label="처리 완료 문서" to="/documents" />
          <StatCard icon={<CircleX size={20} />} color="danger" value={show(stats?.failed)} label="처리 실패 문서" to="/documents" />
          {isStaff ? (
            <StatCard
              icon={<UserPlus size={20} />}
              color="warning"
              value={show(stats?.pendingUsers)}
              label="승인 대기 사용자"
              to="/admin/users?is_active=false"
            />
          ) : (
            <StatCard icon={<ShieldCheck size={20} />} color="brand" value={user ? ROLE_LABELS[user.role] : "-"} label="내 권한" to="/account" />
          )}
        </div>

        <div className="grid-3-1">
          {/* 2. 최근 등록 문서 */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <FileText size={17} /> 최근 등록 문서
              </div>
              <Link to="/documents" className="muted" style={{ fontSize: 13 }}>
                전체 보기
              </Link>
            </div>
            {stats && stats.recent.length > 0 ? (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>파일명</th>
                      <th className="right">크기</th>
                      <th className="right">청크</th>
                      <th className="center">상태</th>
                      <th>등록일</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.recent.map((document) => (
                      <tr key={document.id} className="clickable" onClick={() => navigate("/documents")}>
                        <td style={{ fontWeight: 600 }}>{document.filename}</td>
                        <td className="right">{formatBytes(document.file_size)}</td>
                        <td className="right">{formatNumber(document.chunk_count)}</td>
                        <td className="center">
                          <Badge tone={DOCUMENT_STATUS[document.status].tone}>{DOCUMENT_STATUS[document.status].label}</Badge>
                        </td>
                        <td className="muted">{formatDateTime(document.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                icon={loading ? <Spinner size={22} /> : <FileText size={26} />}
                title={loading ? "불러오는 중..." : "등록된 문서가 없습니다."}
                description={loading ? undefined : "문서 관리 화면에서 .txt, .md 파일을 올려 보세요."}
              />
            )}
          </div>

          <div className="stack">
            {/* 3. 서버 상태 */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <Server size={17} /> 서버 상태
                </div>
              </div>
              <div className="card-body" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span>백엔드 API</span>
                {stats?.healthy === undefined || loading ? (
                  <Spinner />
                ) : stats.healthy ? (
                  <Badge tone="success">정상</Badge>
                ) : (
                  <Badge tone="danger">연결 실패</Badge>
                )}
              </div>
            </div>

            {/* 4. RAG 진행 단계 */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <Workflow size={17} /> RAG 개발 진행 단계
                </div>
              </div>
              <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {ROADMAP.map((step) => (
                  <div key={step.label} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                    <span style={{ fontSize: 13 }}>{step.label}</span>
                    <Badge tone={step.done ? "success" : "neutral"}>{step.done ? "완료" : "준비중"}</Badge>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
