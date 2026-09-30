// [수정] 새 파일 추가 - 페이지 번호 부품
//  - 기존: 없음
//  - 변경: 목록 아래의 "전체 N건 · 이전 1 2 3 다음" 영역
//    - 현재 페이지를 중심으로 최대 5개의 페이지 번호를 보여줌

import { ChevronLeft, ChevronRight } from "lucide-react";

import { formatNumber } from "../../utils/format";

interface PaginationProps {
  page: number; // 현재 페이지 (1부터 시작)
  totalPages: number; // 전체 페이지 수
  total: number; // 전체 항목 수
  onChange: (page: number) => void; // 페이지를 바꿀 때 호출
}

export function Pagination({ page, totalPages, total, onChange }: PaginationProps) {
  // 보여줄 페이지 번호 계산 (예: 현재 7페이지, 전체 20페이지 => 5 6 7 8 9)
  const last = Math.max(totalPages, 1);
  const start = Math.max(1, Math.min(page - 2, last - 4));
  const end = Math.min(last, start + 4);
  const pages = Array.from({ length: end - start + 1 }, (_, index) => start + index);

  return (
    <div className="pagination">
      <span className="muted">
        전체 <strong>{formatNumber(total)}</strong>건 · {page} / {last} 페이지
      </span>
      <div className="pagination-buttons">
        <button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="이전 페이지">
          <ChevronLeft size={14} />
        </button>
        {pages.map((number) => (
          <button
            key={number}
            type="button"
            className={number === page ? "active" : undefined}
            onClick={() => onChange(number)}
          >
            {number}
          </button>
        ))}
        <button type="button" disabled={page >= last} onClick={() => onChange(page + 1)} aria-label="다음 페이지">
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}
