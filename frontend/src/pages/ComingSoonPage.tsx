//  * 준비 중인 메뉴의 안내 화면
//  - 아직 구현되지 않은 메뉴(menu.ts의 ready: false)를 누르면 이 화면이 보임
//    - 메뉴에 적어둔 plan(구현 예정 단계, 설명, 주요 기능)을 보여줌

import { Link } from "react-router-dom";
import { Construction } from "lucide-react";

import type { MenuItem } from "../constants/menu";
import { Badge } from "../components/ui/Badge";

export function ComingSoonPage({ item }: { item: MenuItem }) {
  const Icon = item.icon;
  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-row">
          <h1 className="page-title">{item.label}</h1>
          <Badge tone="warning">준비중</Badge>
        </div>
      </div>

      <div className="card" style={{ maxWidth: 720 }}>
        <div className="card-body form-stack" style={{ padding: 28 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <span className="stat-icon" style={{ background: "var(--warning-soft)", color: "var(--warning)" }}>
              <Construction size={22} />
            </span>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 800, fontSize: 16 }}>
                <Icon size={18} /> {item.label}
              </div>
              <div className="muted" style={{ fontSize: 13 }}>
                {item.plan?.stage ?? "추후 구현 예정"}
              </div>
            </div>
          </div>

          {item.plan && (
            <>
              <p style={{ lineHeight: 1.7 }}>{item.plan.description}</p>
              <div>
                <strong style={{ fontSize: 13 }}>주요 기능 (예정)</strong>
                <ul style={{ margin: "8px 0 0", paddingLeft: 20, lineHeight: 1.9 }}>
                  {item.plan.features.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
              </div>
            </>
          )}

          <div>
            <Link to="/" className="btn btn-outline">
              대시보드로 돌아가기
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
