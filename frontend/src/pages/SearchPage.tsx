// 문서 검색 화면
//  - 질문을 입력하면 의미가 비슷한 문서 청크를 찾아서 보여줌 (POST /search/)
//    - 결과마다 순위, 출처(파일명, 청크 번호), 유사도 점수, 청크 원문을 표시
//    - 질문에 들어 있는 단어는 원문에서 강조 표시
//    - 주소에 ?q=질문 이 있으면 자동으로 검색 (AI Copilot 창의 "자세히 보기"에서 이동할 때)
//  - LLM 답변 전 단계: 챗봇이 "어떤 문서를 근거로 답할지"를 미리 확인하는 화면

import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { FileText, Search, SearchX, Timer } from "lucide-react";

import { ApiError } from "../api/client";
import { listDocuments } from "../api/documents";
import { searchDocuments } from "../api/search";
import type { DocumentItem, SearchResult } from "../api/types";
import { Badge } from "../components/ui/Badge";
import { Alert, EmptyState, Spinner } from "../components/ui/Feedback";
import { formatNumber } from "../utils/format";

// 예시 질문 (md 폴더의 테스트 문서 내용과 관련된 질문들)
const SAMPLE_QUESTIONS = [
  "부모님이 돌아가시면 휴가는 며칠이고 경조금은 얼마인가요?",
  "반반차는 한 달에 몇 번까지 쓸 수 있어?",
  "직원을 해고하려면 며칠 전에 미리 알려줘야 하나요?",
  "2031년 AI 에이전트 시장 규모 전망은?",
];

// 결과 개수 선택지
const TOP_K_OPTIONS = [3, 5, 10, 20];

const errorMessage = (error: unknown) =>
  error instanceof ApiError ? error.message : "알 수 없는 오류가 발생했습니다.";

// 유사도 점수 => 막대 색상 (높을수록 초록, 낮을수록 회색)
//  - 기준값은 bge-m3로 테스트 문서를 검색해 본 경험치 (절대적인 기준은 아님)
function scoreTone(score: number): string {
  if (score >= 0.6) return "var(--success)";
  if (score >= 0.45) return "var(--warning)";
  return "var(--text-subtle)";
}

// 원문에서 질문 단어를 강조 표시 (<mark>)
//  - 질문을 띄어쓰기로 나눈 단어 중 2글자 이상인 것만 강조 (예: "휴가는" "며칠이고")
//  - 조사가 붙은 단어("휴가는")도 앞부분("휴가")이 맞으면 강조되도록, 단어의 앞 2글자 이상을 사용
function highlight(text: string, query: string): ReactNode {
  const words = Array.from(
    new Set(
      query
        .split(/\s+/)
        .map((word) => word.replace(/[?!.,]/g, ""))
        .filter((word) => word.length >= 2)
        // 조사 등을 떼기 위해 단어의 앞부분(최대 앞 2글자 이상, 마지막 글자 제외)만 사용
        .map((word) => (word.length >= 3 ? word.slice(0, -1) : word)),
    ),
  );
  if (words.length === 0) return text;
  // 특수문자를 글자 그대로 찾도록 처리한 뒤, 단어들 중 하나라도 맞으면 나눔
  const escaped = words.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "g");
  // split에 괄호(그룹)가 있는 정규식을 쓰면, 맞은 부분도 결과 배열에 포함됨 => 홀수 번째가 맞은 부분
  return text.split(pattern).map((part, index) => (index % 2 === 1 ? <mark key={index}>{part}</mark> : part));
}

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [topK, setTopK] = useState(5);
  const [documentId, setDocumentId] = useState<number | "">(""); // "" = 전체 문서
  const [documents, setDocuments] = useState<DocumentItem[]>([]); // 검색 범위 선택용 문서 목록
  const [result, setResult] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 마지막으로 검색한 질문 (주소의 ?q= 가 바뀌었을 때 "새 질문인지" 확인하는 용도)
  //  - useRef: 값이 바뀌어도 화면을 다시 그리지 않는 저장 공간
  const lastSearchedRef = useRef<string | null>(null);

  // 1. 검색 범위 선택용 문서 목록 (처리 완료된 문서만, 최대 100개)
  useEffect(() => {
    listDocuments({ status: "completed", size: 100 })
      .then((page) => setDocuments(page.items))
      .catch(() => setDocuments([]));
  }, []);

  // 2. 검색 실행
  const runSearch = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question) return;
      setSearching(true);
      setError(null);
      // 주소에 질문을 남겨둠 => 새로고침하거나 주소를 공유해도 같은 검색 결과를 볼 수 있음
      //  - 주소를 바꾸기 "전에" 기록해 두어야 아래 3번의 자동 검색이 한 번 더 실행되지 않음
      lastSearchedRef.current = question;
      setSearchParams({ q: question }, { replace: true });
      try {
        setResult(
          await searchDocuments({
            query: question,
            top_k: topK,
            document_ids: documentId === "" ? undefined : [documentId],
          }),
        );
      } catch (err) {
        setError(errorMessage(err));
        setResult(null);
      } finally {
        setSearching(false);
      }
    },
    [topK, documentId, setSearchParams],
  );

  // 3. 주소의 ?q= 질문이 "새 질문"이면 자동으로 검색
  //  - 화면이 처음 열릴 때 (예: 새로고침, AI 창의 "자세히 보기"로 이동)
  //  - 이미 이 화면에 있는데 AI 창에서 다른 질문의 "자세히 보기"를 눌렀을 때
  //  - 방금 검색한 질문과 같으면 다시 검색하지 않음 (runSearch가 주소를 바꿀 때 무한 반복 방지)
  const queryParam = searchParams.get("q");
  useEffect(() => {
    if (queryParam && queryParam !== lastSearchedRef.current) {
      setQuery(queryParam);
      runSearch(queryParam);
    }
  }, [queryParam, runSearch]);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    runSearch(query);
  };

  // 예시 질문 버튼: 입력창에 넣고 바로 검색
  const searchSample = (sample: string) => {
    setQuery(sample);
    runSearch(sample);
  };

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-row">
          <h1 className="page-title">문서 검색</h1>
          <p className="page-desc">질문과 의미가 비슷한 문서 내용을 찾아 보여줍니다. (AI 답변 생성 전 단계)</p>
        </div>
      </div>

      <div className="stack">
        {/* 1. 검색 카드 */}
        <div className="card">
          <form className="card-body form-stack" onSubmit={handleSubmit}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                className="input"
                style={{ flex: 1, minWidth: 260, height: 44, fontSize: 15 }}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="예) 연차는 며칠 전에 신청해야 하나요?"
                maxLength={500}
                aria-label="검색할 질문"
                autoFocus
              />
              <select
                className="select"
                style={{ height: 44 }}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
                aria-label="결과 개수"
              >
                {TOP_K_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    상위 {option}개
                  </option>
                ))}
              </select>
              <select
                className="select"
                style={{ height: 44, maxWidth: 280 }}
                value={documentId}
                onChange={(event) => setDocumentId(event.target.value === "" ? "" : Number(event.target.value))}
                aria-label="검색 범위"
              >
                <option value="">전체 문서</option>
                {documents.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.filename}
                  </option>
                ))}
              </select>
              <button type="submit" className="btn btn-primary" style={{ height: 44 }} disabled={searching || !query.trim()}>
                {searching ? <Spinner size={15} /> : <Search size={15} />} 검색
              </button>
            </div>

            {/* 예시 질문 */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              <span className="muted" style={{ fontSize: 12, marginRight: 4 }}>
                예시 질문
              </span>
              {SAMPLE_QUESTIONS.map((sample) => (
                <button key={sample} type="button" className="chip" onClick={() => searchSample(sample)}>
                  {sample}
                </button>
              ))}
            </div>
          </form>
        </div>

        {error && <Alert tone="error">{error}</Alert>}

        {/* 2. 검색 결과 */}
        {result && (
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                검색 결과 <span className="count-pill">{formatNumber(result.total)}</span>
              </div>
              <span className="muted" style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12 }}>
                <Timer size={14} /> {(result.elapsed_ms / 1000).toFixed(2)}초
              </span>
            </div>

            {result.results.length === 0 ? (
              <EmptyState
                icon={<SearchX size={26} />}
                title="관련 문서를 찾지 못했습니다."
                description="문서 관리에서 문서를 먼저 등록하거나, 검색 범위를 전체 문서로 바꿔 보세요."
              />
            ) : (
              <div className="card-body stack" style={{ gap: 14 }}>
                <Alert tone="info">
                  유사도는 1에 가까울수록 질문과 의미가 비슷하다는 뜻입니다. 지금은 점수가 낮아도 걸러내지 않고 모두 보여줍니다.
                </Alert>
                {result.results.map((hit) => (
                  <div key={`${hit.document_id}-${hit.chunk_index}`} className="search-result">
                    <div className="search-result-head">
                      <span className="rank-badge">{hit.rank}</span>
                      <FileText size={16} className="muted" />
                      <strong>{hit.filename}</strong>
                      <Badge tone="neutral">청크 #{hit.chunk_index}</Badge>
                      {/* 유사도 막대 (0~1 점수를 0~100% 너비로 표시) */}
                      <span className="score">
                        <span className="score-bar">
                          <span
                            className="score-fill"
                            style={{ width: `${Math.max(0, Math.min(1, hit.score)) * 100}%`, background: scoreTone(hit.score) }}
                          />
                        </span>
                        <span className="mono">{hit.score.toFixed(3)}</span>
                      </span>
                    </div>
                    <p className="search-result-text">{highlight(hit.text, result.query)}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {!result && !searching && !error && (
          <div className="card">
            <EmptyState
              icon={<Search size={26} />}
              title="질문을 입력해 검색해 보세요."
              description="등록된 문서에서 질문과 의미가 가장 비슷한 부분을 찾아드립니다."
            />
          </div>
        )}
      </div>
    </div>
  );
}
