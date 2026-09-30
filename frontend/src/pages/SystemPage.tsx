// [수정] 새 파일 추가 - 시스템 상태 화면 (admin, manager 전용)
//  - 기존: 없음
//  - 변경: 백엔드 서버 상태(GET /health-check)와 프론트엔드 연결 정보를 보여줌
//    - Vector DB, 임베딩 서버는 백엔드가 "시작할 때" 연결을 확인하므로,
//      백엔드가 정상이면 두 서버도 정상적으로 연결된 상태라는 뜻

import { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw, Server } from "lucide-react";

import { healthCheck } from "../api/system";
import { Badge } from "../components/ui/Badge";
import { Alert, Spinner } from "../components/ui/Feedback";
import { useTheme } from "../contexts/ThemeContext";
import { formatDateTime } from "../utils/format";

export function SystemPage() {
  const { theme } = useTheme();
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [loading, setLoading] = useState(false);

  // 서버 상태 확인
  const check = useCallback(async () => {
    setLoading(true);
    try {
      const result = await healthCheck();
      setHealthy(result.status === "healthy");
    } catch {
      setHealthy(false);
    } finally {
      setCheckedAt(new Date());
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  // 표시할 연결 구성 정보
  const components = [
    { name: "백엔드 API (FastAPI)", detail: "GET /health-check", status: healthy },
    { name: "PostgreSQL (Supabase)", detail: "백엔드 시작 시 연결 확인", status: healthy },
    { name: "Vector DB (Qdrant)", detail: "백엔드 시작 시 연결 + 컬렉션 확인", status: healthy },
    { name: "임베딩 서버 (bge-m3, CPU)", detail: "백엔드 시작 시 임베딩 테스트", status: healthy },
    { name: "LLM 서버", detail: "④ 챗봇 단계에서 연결 예정", status: undefined },
  ];

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-row">
          <h1 className="page-title">시스템 상태</h1>
          <p className="page-desc">백엔드와 연결된 외부 시스템의 상태를 확인합니다.</p>
        </div>
        <button type="button" className="btn btn-outline" onClick={check} disabled={loading}>
          {loading ? <Spinner size={15} /> : <RefreshCw size={15} />} 다시 확인
        </button>
      </div>

      <div className="stack">
        {healthy === false && (
          <Alert tone="error">
            백엔드 서버에 연결할 수 없습니다. backend 폴더에서 uv run uvicorn src.main:app --reload 로 서버를 켜고,
            임베딩 컨테이너(docker compose up -d embedding)가 켜져 있는지 확인하세요.
          </Alert>
        )}

        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Activity size={17} /> 구성 요소
            </div>
            <span className="muted" style={{ fontSize: 12 }}>
              마지막 확인: {formatDateTime(checkedAt)}
            </span>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>구성 요소</th>
                  <th>확인 방법</th>
                  <th className="center">상태</th>
                </tr>
              </thead>
              <tbody>
                {components.map((component) => (
                  <tr key={component.name}>
                    <td style={{ fontWeight: 600 }}>{component.name}</td>
                    <td className="muted">{component.detail}</td>
                    <td className="center">
                      {component.status === undefined ? (
                        <Badge tone="neutral">준비중</Badge>
                      ) : component.status === null ? (
                        <Spinner />
                      ) : component.status ? (
                        <Badge tone="success">정상</Badge>
                      ) : (
                        <Badge tone="danger">연결 실패</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Server size={17} /> 프론트엔드 정보
            </div>
          </div>
          <div className="card-body">
            <dl className="detail-list">
              <dt>API 주소</dt>
              <dd className="mono">{import.meta.env.VITE_API_BASE_URL ?? "/api"} (개발 서버 프록시 → http://localhost:8000)</dd>
              <dt>실행 모드</dt>
              <dd>{import.meta.env.MODE}</dd>
              <dt>화면 테마</dt>
              <dd>{theme === "light" ? "라이트 모드" : "다크 모드"}</dd>
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}
