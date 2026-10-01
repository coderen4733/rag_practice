// 화면 맨 위 헤더
//  - 로고, 사이드바 접기 버튼, 현재 위치(경로) 표시, 다크 모드 버튼, 알림, AI 창 버튼, 프로필 메뉴

import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Bell,
  ChevronDown,
  ChevronRight,
  KeyRound,
  LogOut,
  Moon,
  PanelLeft,
  Sparkles,
  Sun,
  UserRound,
} from "lucide-react";

import { listUsers } from "../../api/users";
import { useAuth } from "../../contexts/AuthContext";
import { useCopilot } from "../../contexts/CopilotContext";
import { useTheme } from "../../contexts/ThemeContext";
import { findMenuByPath } from "../../constants/menu";
import { ROLE_LABELS, displayName } from "../../utils/format";

interface HeaderProps {
  // sidebarCollapsed
  //  - 사이드바가 접혔는지도 받아서, 헤더의 로고 영역 너비를 사이드바와 똑같이 맞춤
  sidebarCollapsed: boolean; // 사이드바 접힘 여부
  onToggleSidebar: () => void; // 사이드바 접기/펴기
}

export function Header({ sidebarCollapsed, onToggleSidebar }: HeaderProps) {
  const { user, isStaff, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { isOpen: copilotOpen, toggleOpen: toggleCopilot } = useCopilot();
  const location = useLocation();
  const navigate = useNavigate();

  const [menuOpen, setMenuOpen] = useState(false); // 프로필 메뉴 열림 여부
  const [pendingCount, setPendingCount] = useState(0); // 승인 대기 사용자 수
  const profileRef = useRef<HTMLDivElement>(null);

  // 1. 현재 위치 표시 (예: 사내 지식베이스 > 지식베이스 > 문서 관리)
  const { group, item } = findMenuByPath(location.pathname);

  // 2. 승인 대기 사용자 수 (관리자급만, 화면을 이동할 때마다 새로 확인)
  useEffect(() => {
    if (!isStaff) return;
    listUsers({ is_active: false, size: 1 })
      .then((result) => setPendingCount(result.total))
      .catch(() => setPendingCount(0));
  }, [isStaff, location.pathname]);

  // 3. 프로필 메뉴 바깥을 누르면 메뉴 닫기
  useEffect(() => {
    if (!menuOpen) return;
    const handleClick = (event: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  // 메뉴에서 항목을 고르면: 메뉴 닫기 + 이동
  const go = (path: string) => {
    setMenuOpen(false);
    navigate(path);
  };

  const handleLogout = async () => {
    setMenuOpen(false);
    await logout({ notice: "로그아웃되었습니다." });
    navigate("/login");
  };

  return (
    <header className="app-header">
      {/* 왼쪽: 로고 + 사이드바 버튼 + 현재 위치 */}
      <div className="header-left">
        {/* 로고와 사이드바 버튼을 사이드바와 같은 너비의 영역(.header-brand-area)으로 묶음
             - 영역 너비 = 사이드바 너비, 세로선은 영역 오른쪽 끝에 CSS(::after)로 그림
               => 세로선과 사이드바 오른쪽 끝이 항상 같은 위치 (사이드바를 접어도 함께 움직임) */}
        <div className={`header-brand-area ${sidebarCollapsed ? "collapsed" : ""}`}>
          <button
            type="button"
            className="brand"
            style={{ border: "none", background: "none", padding: 0 }}
            onClick={() => navigate("/")}
          >
            ONGYEOL <span className="brand-mark">AI</span>
          </button>
          <button type="button" className="icon-button" onClick={onToggleSidebar} aria-label="사이드바 접기/펴기">
            <PanelLeft size={19} />
          </button>
        </div>
        <nav className="breadcrumb" aria-label="현재 위치">
          <span>사내 지식베이스</span>
          {group && (
            <>
              <ChevronRight size={14} />
              <span>{group}</span>
            </>
          )}
          <ChevronRight size={14} />
          <strong>{item?.label ?? "페이지"}</strong>
        </nav>
      </div>

      {/* 오른쪽: 테마, 알림, AI 창, 프로필 */}
      <div className="header-right">
        <button
          type="button"
          className="icon-button"
          onClick={toggleTheme}
          aria-label={theme === "light" ? "다크 모드로 전환" : "라이트 모드로 전환"}
          title={theme === "light" ? "다크 모드" : "라이트 모드"}
        >
          {theme === "light" ? <Moon size={19} /> : <Sun size={19} />}
        </button>

        {/* 알림: 관리자급에게만 승인 대기 사용자 수를 표시, 누르면 승인 대기 목록으로 이동 */}
        {isStaff && (
          <button
            type="button"
            className="icon-button"
            onClick={() => navigate("/admin/users?is_active=false")}
            aria-label={`승인 대기 사용자 ${pendingCount}명`}
            title={`승인 대기 사용자 ${pendingCount}명`}
          >
            <Bell size={19} />
            {pendingCount > 0 && <span className="icon-badge">{pendingCount}</span>}
          </button>
        )}

        <button
          type="button"
          className={`icon-button ${copilotOpen ? "active" : ""}`}
          onClick={toggleCopilot}
          aria-label="AI Copilot 창 열기/닫기"
          title="AI Copilot"
        >
          <Sparkles size={19} />
        </button>

        {/* 프로필 + 드롭다운 메뉴 */}
        {user && (
          <div className="profile" ref={profileRef}>
            <button type="button" className="profile-button" onClick={() => setMenuOpen((open) => !open)}>
              <span className="avatar">{user.email.charAt(0).toUpperCase()}</span>
              {/* 버튼 안에는 div를 넣을 수 없어서 span을 사용 (CSS에서 줄바꿈되게 처리) */}
              <span className="profile-text">
                <span className="profile-name">{displayName(user.email)}</span>
                <span className="profile-sub">{ROLE_LABELS[user.role]} · 온결에이아이</span>
              </span>
              {/* profile-chevron - 넓어진 프로필 영역의 오른쪽 끝에 화살표를 붙이기 위함 */}
              <ChevronDown size={16} className="muted profile-chevron" />
            </button>

            {menuOpen && (
              <div className="dropdown" role="menu">
                <div style={{ padding: "8px 10px 10px", borderBottom: "1px solid var(--border)", marginBottom: 6 }}>
                  <div style={{ fontWeight: 700 }}>{user.email}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {ROLE_LABELS[user.role]} 권한
                  </div>
                </div>
                <button type="button" className="dropdown-item" onClick={() => go("/account")}>
                  <UserRound size={16} /> 내 계정
                </button>
                <button type="button" className="dropdown-item" onClick={() => go("/account#password")}>
                  <KeyRound size={16} /> 비밀번호 변경
                </button>
                <button type="button" className="dropdown-item" onClick={toggleTheme}>
                  {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
                  {theme === "light" ? "다크 모드" : "라이트 모드"}
                </button>
                <button type="button" className="dropdown-item text-danger" onClick={handleLogout}>
                  <LogOut size={16} /> 로그아웃
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
