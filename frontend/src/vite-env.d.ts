// [수정] 새 파일 추가 - Vite 환경 변수의 타입 정의
//  - 기존: 없음
//  - 변경: import.meta.env.VITE_API_BASE_URL 을 사용할 때 타입 검사가 되도록 선언
/// <reference types="vite/client" />

interface ImportMetaEnv {
  // API 기본 주소 (기본값 "/api" => Vite 프록시 또는 Nginx를 통해 백엔드로 전달)
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
