// 주소(URL)와 화면(페이지) 연결
//  - 주소마다 어떤 화면을 보여줄지 정함
//    - /login           : 로그인/회원가입 (로그인한 사용자는 대시보드로 보냄)
//    - 그 외 모든 주소  : 로그인이 필요함 (로그인 안 했으면 /login 으로 보냄)
//    - 관리 메뉴        : admin, manager 만 볼 수 있음
//    - 준비 중 메뉴     : ComingSoonPage (menu.ts의 ready: false 인 메뉴를 자동으로 연결)

import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AppLayout } from "./components/layout/AppLayout";
import { Alert, Spinner } from "./components/ui/Feedback";
import { ALL_MENU_ITEMS } from "./constants/menu";
import { useAuth } from "./contexts/AuthContext";
import { AccountPage } from "./pages/AccountPage";
import { AuthPage } from "./pages/AuthPage";
import { ComingSoonPage } from "./pages/ComingSoonPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { SearchPage } from "./pages/SearchPage";
import { ChatPage } from "./pages/ChatPage";
import { SystemPage } from "./pages/SystemPage";
import { UsersPage } from "./pages/UsersPage";

// 로그인 여부 확인 중일 때 보여주는 화면
function FullScreenLoading() {
  return (
    <div className="auth-page">
      <Spinner size={28} />
    </div>
  );
}

// 로그인이 필요한 화면을 감싸는 부품
//  - 로그인 안 했으면 /login 으로 보내면서, 원래 가려던 주소(from)를 함께 넘김
//    => 로그인 후 그 주소로 다시 보내줌
function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <FullScreenLoading />;
  if (status === "guest") return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}

// 관리자급(admin, manager)만 볼 수 있는 화면을 감싸는 부품
function RequireStaff({ children }: { children: ReactNode }) {
  const { isStaff } = useAuth();
  if (!isStaff) {
    return (
      <div className="page">
        <Alert tone="error">이 화면은 관리자·매니저만 사용할 수 있습니다.</Alert>
      </div>
    );
  }
  return <>{children}</>;
}

// 로그인 화면: 이미 로그인한 사용자는 대시보드로 보냄
function GuestOnly({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  if (status === "loading") return <FullScreenLoading />;
  if (status === "authenticated") return <Navigate to="/" replace />;
  return <>{children}</>;
}

// 준비 중인 메뉴 목록 (주소 -> 안내 화면 자동 연결)
const COMING_SOON_ITEMS = ALL_MENU_ITEMS.filter((item) => !item.ready);

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={
            <GuestOnly>
              <AuthPage />
            </GuestOnly>
          }
        />

        {/* 로그인 후 화면: AppLayout(헤더+사이드바+AI 창) 안에 각 페이지가 그려짐 */}
        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="documents" element={<DocumentsPage />} />
          {/* 문서 검색 화면 연결 (기존: 준비 중 안내 화면) */}
          <Route path="search" element={<SearchPage />} />
          {/* 챗봇 화면 연결 (기존: 준비 중 안내 화면) */}
          <Route path="chat" element={<ChatPage />} />
          <Route path="account" element={<AccountPage />} />
          <Route
            path="admin/users"
            element={
              <RequireStaff>
                <UsersPage />
              </RequireStaff>
            }
          />
          <Route
            path="admin/system"
            element={
              <RequireStaff>
                <SystemPage />
              </RequireStaff>
            }
          />
          {/* 준비 중인 메뉴들 (예: /search, /chat) */}
          {COMING_SOON_ITEMS.map((item) => (
            <Route key={item.path} path={item.path.slice(1)} element={<ComingSoonPage item={item} />} />
          ))}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
