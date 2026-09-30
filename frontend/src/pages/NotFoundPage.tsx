// [수정] 새 파일 추가 - 없는 주소로 들어왔을 때 보여주는 화면 (404)
//  - 기존: 없음

import { Link } from "react-router-dom";
import { SearchX } from "lucide-react";

import { EmptyState } from "../components/ui/Feedback";

export function NotFoundPage() {
  return (
    <div className="page">
      <div className="card">
        <EmptyState icon={<SearchX size={30} />} title="페이지를 찾을 수 없습니다." description="주소가 올바른지 확인해 주세요." />
        <div style={{ display: "flex", justifyContent: "center", paddingBottom: 28 }}>
          <Link to="/" className="btn btn-outline">
            대시보드로 이동
          </Link>
        </div>
      </div>
    </div>
  );
}
