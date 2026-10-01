#  * 대화 메시지를 보낸 쪽(ChatMessageRole) 정의
#  - 대화 이력을 저장하면서 "누가 보낸 메시지인지" 구분하는 값
#    - user     : 사용자가 보낸 질문
#    - assistant: AI가 만든 답변
#  - 값을 "user", "assistant"로 정한 이유:
#    LLM API(OpenAI 호환)의 메시지 역할(role) 이름과 같아서, 이전 대화를 LLM에게 보낼 때
#    값을 바꾸지 않고 그대로 쓸 수 있음

from enum import Enum


class ChatMessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
