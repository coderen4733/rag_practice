// [수정] 새 파일 추가 - 왼쪽 메뉴 구성
//  - 기존: 없음
//  - 변경: 전체 프로젝트 구조에 필요한 메뉴를 한 곳에 정의
//    - ready: true  => 지금 동작하는 메뉴
//    - ready: false => 아직 구현되지 않은 메뉴 ("준비중" 표시, 누르면 준비 중 안내 화면)
//    - roles        => 이 권한을 가진 사용자에게만 메뉴를 보여줌 (없으면 모두에게 보임)
//  - ⚠️ 새 기능을 완성하면 여기서 ready 를 true 로 바꾸고, App.tsx에 화면을 연결하면 됨

import {
  Bot,
  BookOpen,
  Database,
  FileText,
  Gauge,
  History,
  LayoutDashboard,
  MessagesSquare,
  ScrollText,
  Search,
  Server,
  Settings,
  UserRound,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

import type { Role } from "../api/types";

// 메뉴 항목 1개
export interface MenuItem {
  label: string; // 메뉴 이름
  path: string; // 이동할 주소
  icon: LucideIcon; // 아이콘
  ready: boolean; // 구현 완료 여부
  roles?: Role[]; // 볼 수 있는 권한 (없으면 모두)
  // 준비 중인 메뉴의 안내 화면에 보여줄 설명
  plan?: {
    stage: string; // 구현 예정 단계
    description: string; // 기능 설명
    features: string[]; // 주요 기능 목록
  };
}

// 메뉴 묶음 (예: "지식베이스" 아래에 여러 메뉴)
export interface MenuGroup {
  label: string;
  icon: LucideIcon;
  items: MenuItem[];
}

// 관리자급 권한 (admin + manager)
const STAFF: Role[] = ["admin", "manager"];

// 묶음 없이 맨 위에 보이는 메뉴
export const TOP_MENU: MenuItem[] = [
  { label: "대시보드", path: "/", icon: LayoutDashboard, ready: true },
];

// 묶음 메뉴
export const MENU_GROUPS: MenuGroup[] = [
  {
    label: "지식베이스",
    icon: Database,
    items: [
      { label: "문서 관리", path: "/documents", icon: FileText, ready: true },
      {
        label: "문서 검색",
        path: "/search",
        icon: Search,
        ready: false,
        plan: {
          stage: "③ 검색 API 단계에서 구현 예정",
          description:
            "질문을 입력하면 의미가 비슷한 문서 청크를 Vector DB(Qdrant)에서 찾아 보여줍니다. LLM을 붙이기 전에 검색 품질을 먼저 확인하는 화면입니다.",
          features: [
            "질문 임베딩 후 유사도 검색 (상위 N개 청크)",
            "청크 원문, 출처 문서, 유사도 점수 표시",
            "문서/상태별 검색 범위 필터",
          ],
        },
      },
      {
        label: "검색 품질 평가",
        path: "/evaluation",
        icon: Gauge,
        ready: false,
        roles: STAFF,
        plan: {
          stage: "검색 API 완성 후 구현 예정",
          description:
            "질문-정답 평가 세트를 만들어 검색 정확도(Recall@5 등)를 숫자로 확인합니다. 청크 크기나 임베딩 모델을 바꿨을 때 품질을 비교하는 데 사용합니다.",
          features: ["평가용 질문-정답 세트 관리", "검색 정확도 자동 측정", "설정별 결과 비교"],
        },
      },
    ],
  },
  {
    label: "AI 어시스턴트",
    icon: Bot,
    items: [
      {
        label: "챗봇",
        path: "/chat",
        icon: MessagesSquare,
        ready: false,
        plan: {
          stage: "④ 챗봇 단계에서 구현 예정",
          description:
            "검색된 문서 청크를 근거로 LLM(Qwen 등)이 답변하고, 답변과 함께 출처 문서를 보여줍니다. 오른쪽 AI Copilot 창도 이 기능과 연결됩니다.",
          features: ["문서 기반 질의응답 (RAG)", "답변 출처 표시", "답변 스트리밍(글자가 바로바로 표시)"],
        },
      },
      {
        label: "에이전트 스튜디오",
        path: "/agents",
        icon: Workflow,
        ready: false,
        roles: STAFF,
        plan: {
          stage: "챗봇 완성 후 구현 예정",
          description: "회사 업무에 특화된 AI 에이전트를 만들고, 사내 시스템과 연결해 제어합니다.",
          features: ["에이전트 생성/수정", "사용할 도구(문서 검색 등) 연결", "실행 기록 확인"],
        },
      },
      {
        label: "대화 이력",
        path: "/history",
        icon: History,
        ready: false,
        plan: {
          stage: "④ 챗봇 단계에서 구현 예정",
          description: "지금까지 AI와 나눈 대화를 다시 보고 이어서 질문할 수 있습니다.",
          features: ["대화 목록/검색", "대화 이어하기", "대화 삭제"],
        },
      },
    ],
  },
  {
    label: "관리",
    icon: Settings,
    items: [
      {
        label: "사용자·권한 관리",
        path: "/admin/users",
        icon: Users,
        ready: true,
        roles: STAFF,
      },
      {
        label: "시스템 상태",
        path: "/admin/system",
        icon: Server,
        ready: true,
        roles: STAFF,
      },
      {
        label: "감사 로그",
        path: "/admin/audit",
        icon: ScrollText,
        ready: false,
        roles: STAFF,
        plan: {
          stage: "추후 구현 예정",
          description: "누가 언제 어떤 작업(로그인, 문서 삭제, 권한 변경 등)을 했는지 기록하고 조회합니다.",
          features: ["작업 기록 목록", "사용자/기간별 필터", "기록 내보내기"],
        },
      },
    ],
  },
];

// 묶음 없이 맨 아래에 보이는 메뉴
export const BOTTOM_MENU: MenuItem[] = [
  { label: "내 계정", path: "/account", icon: UserRound, ready: true },
  {
    label: "사용 가이드",
    path: "/guide",
    icon: BookOpen,
    ready: false,
    plan: {
      stage: "추후 구현 예정",
      description: "처음 사용하는 사람을 위한 기능별 사용 방법 안내입니다.",
      features: ["문서 등록 방법", "권한별 사용 가능한 기능", "자주 묻는 질문"],
    },
  },
];

// 모든 메뉴 항목을 한 줄로 모은 목록 (주소로 메뉴를 찾을 때 사용)
export const ALL_MENU_ITEMS: MenuItem[] = [
  ...TOP_MENU,
  ...MENU_GROUPS.flatMap((group) => group.items),
  ...BOTTOM_MENU,
];

// 현재 주소(path)에 해당하는 메뉴와 묶음 이름 찾기 (헤더의 경로 표시에 사용)
export function findMenuByPath(path: string): { group?: string; item?: MenuItem } {
  for (const group of MENU_GROUPS) {
    const item = group.items.find((menu) => menu.path === path);
    if (item) return { group: group.label, item };
  }
  return { item: ALL_MENU_ITEMS.find((menu) => menu.path === path) };
}

// 사용자 권한으로 이 메뉴를 볼 수 있는지 확인
export function canSeeMenu(item: MenuItem, role: Role | undefined): boolean {
  return !item.roles || (role !== undefined && item.roles.includes(role));
}
