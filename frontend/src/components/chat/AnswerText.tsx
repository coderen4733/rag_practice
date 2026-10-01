// AI 답변 표시 부품
//  - AI 답변 글을 보기 좋게 바꿔서 보여줌 (챗봇 화면, AI Copilot 창에서 함께 사용)
//    - [1], [2] 같은 출처 번호 => 누를 수 있는 작은 동그라미 버튼 (누르면 해당 근거 문서로 이동)
//    - **굵게** => 굵은 글씨 (프롬프트로 마크다운을 쓰지 말라고 했지만 모델이 가끔 사용함)
//    - 줄바꿈은 CSS(white-space: pre-wrap)로 그대로 보여줌
//    - streaming=true 이면 글 끝에 깜빡이는 커서(▍)를 붙여 "작성 중"임을 보여줌

import type { ReactNode } from "react";

// 출처 번호([1]) 또는 굵은 글씨(**글자**)를 찾는 정규식
//  - 괄호(그룹)로 감싸서 split 결과에 찾은 부분도 포함되게 함
const TOKEN_PATTERN = /(\[\d+\]|\*\*[^*\n]+\*\*)/g;

interface AnswerTextProps {
  text: string;
  streaming?: boolean; // 답변 작성 중인지
  onCitationClick?: (number: number) => void; // 출처 번호를 눌렀을 때
}

export function AnswerText({ text, streaming = false, onCitationClick }: AnswerTextProps) {
  // 글을 "일반 글자 / 출처 번호 / 굵은 글씨" 조각으로 나눈 뒤 각각 알맞게 그림
  const parts: ReactNode[] = text.split(TOKEN_PATTERN).map((part, index) => {
    // 1. 출처 번호 [1]
    const citation = part.match(/^\[(\d+)\]$/);
    if (citation) {
      const number = Number(citation[1]);
      return (
        <button
          key={index}
          type="button"
          className="citation"
          onClick={() => onCitationClick?.(number)}
          title={`근거 문서 ${number}번 보기`}
          disabled={!onCitationClick}
        >
          {number}
        </button>
      );
    }
    // 2. 굵은 글씨 **글자**
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    // 3. 일반 글자
    return part;
  });

  return (
    <div className="answer-text">
      {parts}
      {streaming && <span className="typing-cursor">▍</span>}
    </div>
  );
}
