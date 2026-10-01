// 타자 치듯 글자를 하나씩 보여주는 기능 (React Hook)
//  - 도착한 글자를 "일정한 속도로 조금씩" 보여줌
//
// 📌 왜 필요한가?
//  - 맥북에서 LLM은 참고 문서를 읽는 데 약 6초, 짧은 답변을 쓰는 데 약 0.5초가 걸림
//    => 답변 조각이 0.5초 안에 한꺼번에 몰려와서, 화면에서는 "한 번에 나타난 것"처럼 보임
//  - 도착한 글자를 모아뒀다가 1프레임(약 1/60초)마다 조금씩 보여주면, 작성되는 과정이 눈에 보임
//
// 📌 속도 조절
//  - 아직 보여주지 못한 글자(밀린 글자)가 적으면: 1프레임에 1글자 (= 1초에 약 60글자)
//  - 밀린 글자가 많으면: 자동으로 빨라짐 (긴 답변 때문에 화면이 실제보다 너무 늦어지지 않도록)
//
// 📌 Hook이란?
//  - use로 시작하는 함수로, 화면 부품(컴포넌트) 안에서 상태(useState) 등을 묶어서 재사용하는 방법

import { useEffect, useState } from "react";

// 밀린 글자 수를 이 값으로 나눈 만큼 한 프레임에 보여줌 (작을수록 빨리 따라잡음)
const CATCH_UP_DIVISOR = 60;

// 사용법: const { shown, typing } = useTypewriter(지금까지 받은 답변, 답변 받는 중인지)
//  - shown : 지금 화면에 보여줄 글자
//  - typing: 아직 보여줄 글자가 남았거나 답변을 받는 중인지 (깜빡이는 커서 표시용)
export function useTypewriter(text: string, streaming: boolean): { shown: string; typing: boolean } {
  // 지금까지 보여준 글자 수
  //  - 처음부터 다 받은 상태(예: 예전 메시지를 다시 그릴 때)면 바로 전부 보여줌
  const [length, setLength] = useState(() => (streaming ? 0 : text.length));

  useEffect(() => {
    // 다 보여줬으면 멈춤 (새 글자가 도착해서 text가 길어지면 이 함수가 다시 실행됨)
    if (length >= text.length) return;
    // requestAnimationFrame: 브라우저가 다음 화면을 그릴 때(약 1/60초 뒤) 함수를 실행
    //  - 그 사이에 새 글자가 도착하면 아래 return의 cancel로 예약이 취소되고,
    //    새 text 기준으로 다시 예약되므로 항상 최신 글자를 기준으로 계산함
    const frame = requestAnimationFrame(() => {
      setLength((current) => {
        const target = text.length;
        const backlog = target - current; // 밀린 글자 수
        const step = Math.max(1, Math.ceil(backlog / CATCH_UP_DIVISOR));
        return Math.min(target, current + step);
      });
    });
    // 화면이 사라지거나 다시 실행되기 전에 예약을 취소 (중복 실행 방지)
    return () => cancelAnimationFrame(frame);
  }, [length, text]);

  // 답변이 처음부터 다시 시작된 경우(글이 짧아짐) 대비
  const safeLength = Math.min(length, text.length);
  return { shown: text.slice(0, safeLength), typing: streaming || safeLength < text.length };
}
