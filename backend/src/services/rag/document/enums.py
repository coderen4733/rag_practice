#  * 문서 처리 상태(DocumentStatus) 정의
#  - 문서가 "처리 중 / 완료 / 실패" 중 어떤 상태인지 나타내는 값
#    - processing: 업로드되어 청크 분할/임베딩/저장을 진행하는 중
#    - completed : Qdrant에 모든 청크 저장 완료 (검색 가능)
#    - failed    : 임베딩 서버나 Vector DB 문제로 처리 실패 (검색 불가, 삭제 후 다시 업로드)
#  - 지금은 업로드 요청 안에서 바로 처리하므로 processing은 잠깐만 보이지만,
#    나중에 Celery 백그라운드 처리를 추가하면 "처리 중" 상태를 화면에 보여줄 때 사용

from enum import Enum


class DocumentStatus(Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
