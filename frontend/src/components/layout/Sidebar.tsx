// 왼쪽 메뉴(사이드바)
//  - constants/menu.ts 에 정의된 메뉴를 그림
//    - 권한(roles)이 맞지 않는 메뉴는 숨김
//    - 아직 구현되지 않은 메뉴(ready: false)는 "준비중" 표시
//    - collapsed(접힘)일 때는 아이콘만 보임

import { useState } from "react";
import { NavLink } from "react-router-dom";
import { ChevronDown, FolderOpen } from "lucide-react";

import { useAuth } from "../../contexts/AuthContext";
import {
  BOTTOM_MENU,
  MENU_GROUPS,
  TOP_MENU,
  canSeeMenu,
  type MenuItem,
} from "../../constants/menu";

// 메뉴 항목 1개 그리기
function NavItem({ item }: { item: MenuItem }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.path}
      // end: "/" 메뉴가 모든 주소("/documents" 등)에서 선택된 것처럼 보이지 않도록 정확히 일치할 때만 선택
      end={item.path === "/"}
      // isActive: 현재 주소가 이 메뉴의 주소면 true => "active" 스타일 적용
      className={({ isActive }) => `nav-item ${isActive ? "active" : ""} ${item.ready ? "" : "soon"}`}
      title={item.ready ? item.label : `${item.label} (준비중)`}
    >
      <Icon size={18} style={{ flexShrink: 0 }} />
      <span className="nav-label">{item.label}</span>
      {!item.ready && <span className="pill-soon">준비중</span>}
    </NavLink>
  );
}

export function Sidebar({ collapsed }: { collapsed: boolean }) {
  const { user } = useAuth();
  const role = user?.role;

  // 묶음별 펼침 상태 (처음에는 모두 펼침) - 예: { "지식베이스": true, "관리": false }
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const isGroupOpen = (label: string) => openGroups[label] ?? true;
  const toggleGroup = (label: string) =>
    setOpenGroups((current) => ({ ...current, [label]: !isGroupOpen(label) }));

  return (
    <aside className={`app-sidebar ${collapsed ? "collapsed" : ""}`}>
      {/* 프로젝트 선택 (지금은 프로젝트가 하나뿐이라 표시만 함) */}
      <button type="button" className="project-card" title="프로젝트: 사내 지식베이스">
        <FolderOpen size={20} style={{ flexShrink: 0, color: "var(--brand)" }} />
        {/* 버튼 안에는 div를 넣을 수 없어서 span을 사용 (CSS에서 줄바꿈되게 처리) */}
        <span className="project-text" style={{ flex: 1 }}>
          <span className="project-label">프로젝트</span>
          <span className="project-name">사내 지식베이스</span>
        </span>
        <ChevronDown size={16} className="chevron muted" />
      </button>

      <nav aria-label="주 메뉴">
        {/* 1. 맨 위 메뉴 (대시보드) */}
        {TOP_MENU.filter((item) => canSeeMenu(item, role)).map((item) => (
          <NavItem key={item.path} item={item} />
        ))}

        {/* 2. 묶음 메뉴 (지식베이스, AI 어시스턴트, 관리) */}
        {MENU_GROUPS.map((group) => {
          const items = group.items.filter((item) => canSeeMenu(item, role));
          if (items.length === 0) return null; // 볼 수 있는 메뉴가 없으면 묶음도 숨김
          const GroupIcon = group.icon;
          const open = isGroupOpen(group.label);
          return (
            <div className="nav-group" key={group.label}>
              <button
                type="button"
                className="nav-group-title"
                onClick={() => toggleGroup(group.label)}
                aria-expanded={open}
                title={group.label}
              >
                <GroupIcon size={18} style={{ flexShrink: 0 }} />
                <span className="nav-label">{group.label}</span>
                <ChevronDown size={16} className={`chevron ${open ? "open" : ""}`} />
              </button>
              {open && (
                <div className="nav-sub">
                  {items.map((item) => (
                    <NavItem key={item.path} item={item} />
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {/* 3. 맨 아래 메뉴 (내 계정, 사용 가이드) */}
        <div style={{ marginTop: 14, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
          {BOTTOM_MENU.filter((item) => canSeeMenu(item, role)).map((item) => (
            <NavItem key={item.path} item={item} />
          ))}
        </div>
      </nav>
    </aside>
  );
}
