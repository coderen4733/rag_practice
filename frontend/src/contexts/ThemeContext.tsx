// * 라이트/다크 모드 상태 관리
//  - 테마를 바꾸면 <html data-theme="dark"> 로 바뀌고, global.css의 색상 변수가 다크 값으로 바뀜
//
// 📌 Context(컨텍스트)란?
//  - 여러 화면(컴포넌트)이 함께 써야 하는 값을 "한 곳"에 두고 어디서든 꺼내 쓰는 React 기능
//  - 예) 헤더의 테마 버튼과 모든 화면의 색상이 같은 "테마" 값을 공유

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type Theme = "light" | "dark";

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
}

const THEME_KEY = "rag.theme"; // 브라우저 저장소에 테마를 저장할 때 쓰는 이름

const ThemeContext = createContext<ThemeContextValue | null>(null);

// 처음 테마 정하기: 저장된 값 > 운영체제 설정(다크 모드 여부) > 라이트
function getInitialTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // 저장소를 쓸 수 없는 환경이면 아래로 진행
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  // 테마가 바뀔 때마다 <html data-theme="..."> 변경 + 저장
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      // 저장할 수 없으면 무시 (새로고침하면 기본 테마로 돌아감)
    }
  }, [theme]);

  // useCallback: 화면이 다시 그려져도 같은 함수를 재사용 (불필요한 다시 그리기 방지)
  const toggleTheme = useCallback(() => {
    setTheme((current) => (current === "light" ? "dark" : "light"));
  }, []);

  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>;
}

// 사용법: const { theme, toggleTheme } = useTheme();
export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme은 ThemeProvider 안에서만 사용할 수 있습니다.");
  return context;
}
