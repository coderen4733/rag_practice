// 근거 문서 카드 목록 (챗봇 화면, AI Copilot 창에서 함께 사용)
//  - 답변 "위"에 근거 문서 카드를 보여줌
//    - 카드 맨 위 왼쪽: 번호 + 유사도(점수에 따라 색이 다른 캡슐 모양)
//    - 그 아래: 파일명 · 청크 번호
//    - 원문은 숨겨두고 "자세히 보기" 버튼으로 펼치기/접기
//    - LLM이 근거 문서를 읽는 동안 "지금 읽고 있을 것으로 예상되는 문서"를 빨간 테두리로 표시
//
// 📌 "읽는 중" 위치를 어떻게 아는가? (추정값)
//  - LLM 서버는 "지금 몇 번째 문서를 읽는 중"인지 알려주지 않음
//  - 하지만 LLM은 프롬프트를 앞에서부터 순서대로 읽음 (규칙 -> 문서 1 -> 문서 2 ... -> 질문)
//  - 그래서 "지금까지 흐른 시간 x 읽기 속도(글자/초)"로 몇 번째 글자까지 읽었는지 계산하고,
//    각 문서의 글자 수와 비교해서 "지금 읽고 있을 문서"를 추정함
//  - 읽기 속도는 답변할 때마다 실제 걸린 시간으로 보정함 (recordReadingSpeed)

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, ChevronUp, FileText } from "lucide-react";

import type { ChatSource } from "../../api/types";
import { Spinner } from "../ui/Feedback";
import { useNow, type ChatProgressTimes } from "./ChatProgress";

// 근거 문서 카드 1개에 필요한 정보
export interface SourceCardItem {
  number: number; // 답변 안의 [1], [2] 번호
  filename: string;
  chunkIndex: number;
  text: string; // 청크 원문
  score: number; // 유사도
}

// 챗봇 API가 보내준 근거 문서(ChatSource)를 카드 정보로 바꾸기
export function toSourceCardItems(sources: ChatSource[]): SourceCardItem[] {
  return sources.map((source) => ({
    number: source.number,
    filename: source.filename,
    chunkIndex: source.chunk_index,
    text: source.text,
    score: source.score,
  }));
}

// ───────────── 1. 읽기 속도 (글자/초) ─────────────
// 처음 값: 맥북 + Qwen3.5-9B 실측 (참고 문서 약 3,100자를 약 6.3초에 읽음 => 초당 약 450~500자)
const DEFAULT_READING_SPEED = 450;
// 근거 문서 앞에 있는 규칙(system 프롬프트) 등의 글자 수 (대략값) - 이 부분을 먼저 읽음
const PROMPT_OVERHEAD_CHARS = 700;
const SPEED_KEY = "rag.readingSpeed"; // 브라우저에 읽기 속도를 저장할 때 쓰는 이름

// 저장된 읽기 속도 불러오기 (없으면 기본값)
function loadReadingSpeed(): number {
  try {
    const saved = Number(localStorage.getItem(SPEED_KEY));
    return saved > 0 ? saved : DEFAULT_READING_SPEED;
  } catch {
    return DEFAULT_READING_SPEED;
  }
}

let readingSpeed = loadReadingSpeed();

// 실제로 걸린 시간으로 읽기 속도 보정 (첫 답변 조각이 도착했을 때 호출)
//  - sourcesAt: 근거 문서 도착 시각 / firstTokenAt: 첫 답변 조각 도착 시각
//  - 0.5초보다 빠르면 무시: 같은 질문을 다시 하면 LLM이 기억(캐시)해 둔 걸 써서
//    "읽기"를 거의 안 하기 때문에, 그 값으로 보정하면 속도가 엉터리가 됨
//  - 한 번에 확 바꾸지 않고 기존 값과 반씩 섞음 (측정값이 들쭉날쭉해도 안정적으로)
export function recordReadingSpeed(sourcesAt: number, firstTokenAt: number, sources: SourceCardItem[]): void {
  const seconds = (firstTokenAt - sourcesAt) / 1000;
  if (seconds < 0.5 || sources.length === 0) return;
  const totalChars = PROMPT_OVERHEAD_CHARS + sources.reduce((sum, source) => sum + source.text.length, 0);
  readingSpeed = Math.round(readingSpeed * 0.5 + (totalChars / seconds) * 0.5);
  try {
    localStorage.setItem(SPEED_KEY, String(readingSpeed));
  } catch {
    // 저장할 수 없으면 이번 화면에서만 사용
  }
}

// 지금 읽고 있을 것으로 예상되는 문서의 순서(0부터) 계산
//  - 아직 읽기 전이면 -1, 다 읽었으면 sources.length
function estimateReadingIndex(sources: SourceCardItem[], progress: ChatProgressTimes, now: number): number {
  if (progress.sourcesAt === undefined) return -1;
  if (progress.firstTokenAt !== undefined) return sources.length; // 답변 시작 = 다 읽음
  const readChars = ((now - progress.sourcesAt) / 1000) * readingSpeed - PROMPT_OVERHEAD_CHARS;
  if (readChars < 0) return 0; // 규칙을 읽는 중이지만 곧 첫 문서를 읽으므로 첫 문서 표시
  let cumulative = 0;
  for (let index = 0; index < sources.length; index++) {
    cumulative += sources[index].text.length;
    if (readChars < cumulative) return index;
  }
  // 예상보다 오래 걸리는 경우: 마지막 문서를 계속 "읽는 중"으로 표시
  return sources.length - 1;
}

// ───────────── 2. 유사도 캡슐 색상 ─────────────
//  - 기준값은 bge-m3로 테스트 문서를 검색해 본 경험치 (절대적인 기준은 아님)
function scoreClass(score: number): string {
  if (score >= 0.6) return "high";
  if (score >= 0.45) return "mid";
  return "low";
}

// ───────────── 3. 근거 문서 카드 목록 ─────────────
interface SourceCardsProps {
  sources: SourceCardItem[];
  progress?: ChatProgressTimes; // 있으면 "읽는 중" 위치를 표시
  // 답변의 [n]을 눌렀을 때 펼치고 강조할 카드 (같은 번호를 다시 눌러도 동작하도록 시각(at)을 함께 받음)
  focus?: { number: number; at: number } | null;
}

export function SourceCards({ sources, progress, focus }: SourceCardsProps) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set()); // 원문을 펼친 카드 번호들
  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({});

  // "읽는 중"일 때만 0.1초마다 위치를 다시 계산
  const reading =
    progress !== undefined &&
    progress.sourcesAt !== undefined &&
    progress.firstTokenAt === undefined &&
    progress.endedAt === undefined;
  const now = useNow(reading);
  const readingIndex = reading && progress ? estimateReadingIndex(sources, progress, now) : -1;

  // 답변의 [n]을 누르면: 해당 카드 원문을 펼치고 그 위치로 스크롤
  useEffect(() => {
    if (!focus) return;
    setExpanded((current) => new Set(current).add(focus.number));
    cardRefs.current[focus.number]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [focus]);

  // 원문 펼치기/접기
  const toggle = (number: number) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(number)) next.delete(number);
      else next.add(number);
      return next;
    });

  if (sources.length === 0) return null;

  return (
    <div className="source-cards">
      <div className="source-cards-title">
        근거 문서 {sources.length}건
        {reading && <span className="muted"> · 빨간 테두리: 지금 읽고 있을 것으로 예상되는 문서</span>}
      </div>
      {sources.map((source, index) => {
        const isReading = index === readingIndex;
        const isRead = reading && index < readingIndex;
        const isOpen = expanded.has(source.number);
        const isFocused = focus?.number === source.number;
        return (
          <div
            key={source.number}
            ref={(element) => {
              cardRefs.current[source.number] = element;
            }}
            className={`source-card ${isReading ? "reading" : ""} ${isFocused ? "focused" : ""}`}
          >
            {/* 1줄: 번호 + 유사도 캡슐 (+ 읽는 중/읽음 표시) */}
            <div className="source-card-top">
              <span className="citation" style={{ cursor: "default" }}>
                {source.number}
              </span>
              <span className={`score-pill ${scoreClass(source.score)}`}>유사도 {source.score.toFixed(3)}</span>
              {isReading && (
                <span className="source-card-state reading">
                  <Spinner size={12} /> 읽는 중
                </span>
              )}
              {isRead && (
                <span className="source-card-state read">
                  <Check size={12} /> 읽음
                </span>
              )}
            </div>
            {/* 2줄: 파일명 · 청크 번호 */}
            <div className="source-card-title">
              <FileText size={14} className="muted" style={{ flexShrink: 0 }} />
              <span>
                {source.filename} <span className="muted">· 청크 #{source.chunkIndex}</span>
              </span>
            </div>
            {/* 3줄: 원문 펼치기/접기 */}
            <button type="button" className="link-button" onClick={() => toggle(source.number)} aria-expanded={isOpen}>
              {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {isOpen ? "숨기기" : "자세히 보기"}
            </button>
            {isOpen && <p className="source-card-text">{source.text}</p>}
          </div>
        );
      })}
    </div>
  );
}
