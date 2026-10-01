#  * 문서(Document) API의 요청/응답 형식
#  - 문서 등록/조회/목록/삭제 API에서 주고받는 데이터 형식 정의

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.services.rag.document.enums import DocumentStatus


# 문서(Document) 조회(R-D) - 응답(Res)
#  - 문서 등록, 상세 조회, 목록 조회에서 공통으로 사용
class DocumentRes(BaseModel):
    # from_attributes=True:
    # SQLAlchemy 객체를 Pydantic이 자동으로 변환할 수 있도록 설정
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_extension: str
    file_size: int  # 파일 크기 (단위: 바이트)
    status: str  # 처리 상태 (processing / completed / failed)
    chunk_count: int  # Qdrant에 저장된 청크 개수
    error_message: str | None  # 처리 실패 이유 (성공하면 null)
    uploaded_by: int | None  # 업로드한 사용자 id (사용자가 삭제되면 null)
    created_at: datetime
    updated_at: datetime


# 문서(Document) 목록 조회(R-L) - 요청(Query)
#  - 사용자 목록 조회(UserReadListQuery)와 같은 방식
#      예) /documents/?status=failed              => 처리 실패한 문서만
#      예) /documents/?filename=휴가&order=asc     => 파일명에 "휴가" 포함, 오래된 순
class DocumentReadListQuery(BaseModel):
    # 1. 필터(Filter)
    status: DocumentStatus | None = Field(
        default=None,
        description="처리 상태로 필터 (processing / completed / failed)",
    )
    filename: str | None = Field(
        default=None,
        max_length=255,
        description="파일명 부분 검색 (대소문자 구분 없음)",
    )
    # 2. 정렬(Sort) - 등록일(created_at) 기준
    order: Literal["asc", "desc"] = Field(
        default="desc",
        description="정렬 방향 (desc: 최신순 / asc: 오래된순)",
    )
    # 3. 페이지네이션(Pagination)
    page: int = Field(default=1, ge=1, description="페이지 번호 (1부터 시작)")
    size: int = Field(default=20, ge=1, le=100, description="한 페이지당 문서 수 (최대 100)")


# 문서(Document) 목록 조회(R-L) - 응답(Res)
class DocumentReadListRes(BaseModel):
    items: list[DocumentRes]  # 현재 페이지의 문서 목록
    total: int  # 필터 조건에 맞는 전체 문서 수
    page: int  # 현재 페이지 번호
    size: int  # 한 페이지당 문서 수
    total_pages: int  # 전체 페이지 수


# 문서(Document) 삭제(D) - 응답(Res)
class DocumentDeleteRes(BaseModel):
    success: bool = True
    id: int  # 삭제된 문서 id
