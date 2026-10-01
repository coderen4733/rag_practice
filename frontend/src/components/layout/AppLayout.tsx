// 로그인 후 화면의 전체 틀
//  - [헤더] + [사이드바 | 본문 | AI Copilot 창] 배치
//    - <Outlet />: 현재 주소에 맞는 페이지(대시보드, 문서 관리 등)가 이 자리에 그려짐
//    - AI 창을 접으면 화면 오른쪽 가장자리에 다시 여는 탭이 나타남

import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";

import { useCopilot } from "../../contexts/CopilotContext";
import { CopilotPanel } from "./CopilotPanel";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

const SIDEBAR_KEY = "rag.sidebarCollapsed"; // 사이드바 접힘 상태를 저장할 때 쓰는 이름

// 저장된 사이드바 접힘 상태 읽기
function getInitialCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "true";
  } catch {
    return false;
  }
}

export function AppLayout() {
  const { isOpen: copilotOpen, setOpen: setCopilotOpen } = useCopilot();
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(getInitialCollapsed);

  // 사이드바 접힘 상태가 바뀌면 저장 (새로고침해도 유지)
  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, String(sidebarCollapsed));
    } catch {
      // 무시
    }
  }, [sidebarCollapsed]);

  return (
    <div className="app-shell">
      {/* sidebarCollapsed 전달 - 헤더 로고 영역 너비를 사이드바와 맞추기 위함 */}
      <Header
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={() => setSidebarCollapsed((collapsed) => !collapsed)}
      />
      <div className="app-body">
        <Sidebar collapsed={sidebarCollapsed} />
        <main className="app-main">
          <Outlet />
        </main>
        {copilotOpen ? (
          <CopilotPanel />
        ) : (
          // AI 창이 접혀 있을 때: 오른쪽 가장자리의 세로 탭을 누르면 다시 열림
          <button type="button" className="copilot-reopen" onClick={() => setCopilotOpen(true)} aria-label="AI Copilot 창 열기">
            <span className="copilot-avatar">AI</span>
            AI Copilot
          </button>
        )}
      </div>
    </div>
  );
}
