// [수정] 새 파일 추가 - 프론트엔드 시작점
//  - 기존: 없음
//  - 변경: index.html의 <div id="root"> 안에 React 앱을 그림
//    - Provider 순서: 테마 -> 로그인 상태 -> AI 창 (안쪽 부품은 바깥 부품의 값을 사용할 수 있음)

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// 한글 폰트 (npm 패키지에 포함된 파일을 사용 => 인터넷 없는 폐쇄망에서도 동작)
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "./styles/global.css";

import { App } from "./App";
import { AuthProvider } from "./contexts/AuthContext";
import { CopilotProvider } from "./contexts/CopilotContext";
import { ThemeProvider } from "./contexts/ThemeContext";

// StrictMode: 개발 중에 흔한 실수를 찾아 경고해 주는 React 기능 (배포 빌드에는 영향 없음)
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <CopilotProvider>
          <App />
        </CopilotProvider>
      </AuthProvider>
    </ThemeProvider>
  </StrictMode>,
);
