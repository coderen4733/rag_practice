// 챗봇 답변 진행 단계 표시 + 타자 효과 답변 부품
//  - 답변이 만들어지는 과정을 3단계로 나눠서 실시간으로 보여줌
//      ① 관련 문서 검색  ② 근거 문서 읽기  ③ 답변 작성
//    - 진행 중인 단계에는 회전 아이콘과 "흘러가는 시간"을 표시
//    - 끝나면 "검색 0.6초 · 문서 읽기 6.3초 · 답변 작성 0.5초"처럼 한 줄로 요약
//  - 단계 판단 기준 (화면에서 직접 시간을 잼)
//    - sources 이벤트 도착 => ① 검색 끝
//    - 첫 답변 조각 도착   => ② 문서 읽기 끝 (LLM이 참고 문서를 다 읽고 쓰기 시작함)
//    - done/error 도착     => ③ 답변 작성 끝

import { useEffect, useState } from "react";
import { Check, Circle } from "lucide-react";

import { Spinner } from "../ui/Feedback";
import { AnswerText } from "./AnswerText";
import { useTypewriter } from "./useTypewriter";

// 답변 진행 시각 기록 (단위: 밀리초, Date.now() 값)
export interface ChatProgressTimes {
  startedAt: number; // 질문을 보낸 시각
  sourcesAt?: number; // 근거 문서 목록이 도착한 시각 (= 검색 끝)
  firstTokenAt?: number; // 첫 답변 조각이 도착한 시각 (= 문서 읽기 끝)
  endedAt?: number; // 답변이 끝난 시각 (완료, 에러, 중지 모두)
  sourceCount?: number; // 근거 문서 수
}

// 진행 중일 때 0.1초마다 현재 시각을 갱신 (흘러가는 시간 표시용)
export function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(timer); // 끝나면 타이머 정리
  }, [active]);
  return now;
}

// 밀리초 => "1.2초"
const seconds = (ms: number) => `${(Math.max(0, ms) / 1000).toFixed(1)}초`;

// 3단계 각각의 상태와 걸린 시간 계산
function buildSteps(progress: ChatProgressTimes, now: number) {
  const { startedAt, sourcesAt, firstTokenAt, endedAt, sourceCount } = progress;
  // 답변이 끝났으면(endedAt) 그 시각에서 시간을 멈춤
  const until = (time?: number) => time ?? endedAt ?? now;
  return [
    {
      label: "관련 문서 검색",
      done: sourcesAt !== undefined,
      active: sourcesAt === undefined && endedAt === undefined,
      time: until(sourcesAt) - startedAt,
    },
    {
      label: sourceCount ? `근거 문서 ${sourceCount}건 읽기` : "근거 문서 읽기",
      done: firstTokenAt !== undefined,
      active: sourcesAt !== undefined && firstTokenAt === undefined && endedAt === undefined,
      time: sourcesAt !== undefined ? until(firstTokenAt) - sourcesAt : undefined,
    },
    {
      label: "답변 작성",
      done: firstTokenAt !== undefined && endedAt !== undefined,
      active: firstTokenAt !== undefined && endedAt === undefined,
      time: firstTokenAt !== undefined ? until(endedAt) - firstTokenAt : undefined,
    },
  ];
}

// ───────────── 1. 진행 단계 목록 (첫 글자가 나오기 전, 말풍선 안에 표시) ─────────────
export function ChatProgressSteps({ progress }: { progress: ChatProgressTimes }) {
  const now = useNow(progress.endedAt === undefined);
  return (
    <div className="progress-steps">
      {buildSteps(progress, now).map((step) => (
        <div key={step.label} className={`progress-step ${step.active ? "active" : ""} ${step.done ? "done" : ""}`}>
          <span className="progress-icon">
            {step.done ? <Check size={14} /> : step.active ? <Spinner size={14} /> : <Circle size={10} />}
          </span>
          <span>{step.label}</span>
          {step.time !== undefined && <span className="mono progress-time">{seconds(step.time)}</span>}
        </div>
      ))}
    </div>
  );
}

// ───────────── 2. 진행 단계 한 줄 요약 (답변 아래에 표시) ─────────────
//  - 예) 검색 0.6초 · 문서 읽기 6.3초 · 답변 작성 0.5초
export function ChatProgressSummary({ progress }: { progress: ChatProgressTimes }) {
  const now = useNow(progress.endedAt === undefined);
  const [search, read, write] = buildSteps(progress, now);
  const parts = [
    `검색 ${seconds(search.time ?? 0)}`,
    read.time !== undefined ? `문서 읽기 ${seconds(read.time)}` : null,
    write.time !== undefined ? `답변 작성 ${seconds(write.time)}${write.active ? "…" : ""}` : null,
  ].filter(Boolean);
  return <span>{parts.join(" · ")}</span>;
}

// ───────────── 3. 타자 효과 답변 ─────────────
//  - 받은 답변(text)을 useTypewriter로 조금씩 보여주고, AnswerText로 [1] 번호 등을 표시
export function StreamingAnswer({
  text,
  streaming,
  onCitationClick,
}: {
  text: string;
  streaming: boolean;
  onCitationClick?: (number: number) => void;
}) {
  const { shown, typing } = useTypewriter(text, streaming);
  return <AnswerText text={shown} streaming={typing} onCitationClick={onCitationClick} />;
}
