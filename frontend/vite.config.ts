// Vite(프론트엔드 개발 서버 + 빌드 도구) 설정
//  - 개발 서버 포트(3000)와 백엔드 API 프록시(대신 전달) 설정
//
// 📌 프록시(proxy)란?
//  - 브라우저가 http://localhost:3000/api/users/me 로 요청하면
//    Vite 개발 서버가 대신 http://localhost:8000/users/me 로 전달하고 응답을 돌려줌
//  - 브라우저 입장에서는 "같은 주소(3000)"와 통신하므로 CORS 문제가 생기지 않음
//  - 나중에 Docker로 납품할 때는 Nginx가 같은 역할(/api -> 백엔드)을 하면 됨

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  // .env 파일의 값을 읽어옴 (세 번째 인자 ""는 VITE_로 시작하지 않는 값도 읽겠다는 뜻)
  const env = loadEnv(mode, process.cwd(), "");
  // 백엔드 주소 (frontend/.env 에 VITE_API_PROXY_TARGET을 적으면 그 값을 사용)
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://localhost:8000";

  return {
    // React 코드(JSX)를 브라우저가 이해할 수 있게 바꿔주는 플러그인
    plugins: [react()],
    server: {
      port: 3000, // 개발 서버 주소: http://localhost:3000
      strictPort: true, // 3000 포트가 사용 중이면 다른 포트로 바꾸지 않고 에러를 냄
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          // "/api/users/me" -> "/users/me" (앞의 /api를 떼고 백엔드로 전달)
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
    preview: {
      port: 3000,
    },
  };
});
