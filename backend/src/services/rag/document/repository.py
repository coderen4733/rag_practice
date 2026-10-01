#  * 문서(Document) 테이블 DB 작업
#  - documents 테이블 생성/조회/수정/삭제/목록 조회
#  - user/repository.py와 같은 방식: commit은 하지 않고 service에서 함

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.rag.document.enums import DocumentStatus
from src.services.rag.document.models import Document


# 문서(Document) 생성(C)
async def create_document(
    session: AsyncSession,
    document: Document,
) -> Document:
    # 1. Repository -> DB
    session.add(document)
    await session.flush()  # INSERT를 DB에 보내서 id를 발급받음 (확정은 service에서)
    # 2. document 객체 갱신 (DB가 채운 기본값을 다시 읽어옴)
    await session.refresh(document)
    # 3. Repository -> Service
    return document


# 문서(Document) 조회(R-D) by id
async def get_document_by_id(
    session: AsyncSession,
    document_id: int,
) -> Document | None:
    # 1. Repository <- DB
    # id는 PK이므로 session.get() 으로 간단하게 조회 가능 (없으면 None 반환)
    data = await session.get(Document, document_id)
    # 2. Repository -> Service
    return data


# 문서(Document) 수정(U)
#  - service에서 값(status, chunk_count 등)을 바꾼 document 객체를 DB에 반영
async def update_document(
    session: AsyncSession,
    document: Document,
) -> Document:
    # 1. Repository -> DB
    await session.flush()
    # 2. document 객체 갱신 (updated_at은 DB가 정하므로 다시 읽어옴)
    await session.refresh(document)
    # 3. Repository -> Service
    return document


# 문서(Document) 삭제(D)
async def delete_document(
    session: AsyncSession,
    document: Document,
) -> None:
    # 1. Repository -> DB (확정은 service에서 commit)
    await session.delete(document)


# 문서(Document) 목록 조회(R-L)
#  - user/repository.py의 get_users_list와 같은 방식 (필터 + 정렬 + 페이지네이션)
#  - 반환값: (현재 페이지의 문서 목록, 필터 조건에 맞는 전체 문서 수)
async def get_documents_list(
    session: AsyncSession,
    *,
    status: DocumentStatus | None,
    filename: str | None,
    order: str,
    offset: int,
    limit: int,
) -> tuple[list[Document], int]:
    # 1. 필터 조건 만들기 (값이 들어온 조건만 추가)
    conditions = []
    if status is not None:
        conditions.append(Document.status == status)
    if filename:
        # icontains + autoescape: 대소문자 구분 없는 부분 검색, %와 _는 그냥 글자로 취급
        conditions.append(Document.filename.icontains(filename, autoescape=True))

    # 2. Repository <- DB : 전체 개수 조회
    count_query = select(func.count()).select_from(Document).where(*conditions)
    total = await session.scalar(count_query) or 0

    # 3. 정렬 기준 (등록일 + id로 순서 고정)
    if order == "desc":
        order_by = [Document.created_at.desc(), Document.id.desc()]
    else:
        order_by = [Document.created_at.asc(), Document.id.asc()]

    # 4. Repository <- DB : 현재 페이지의 문서 목록 조회
    query = select(Document).where(*conditions).order_by(*order_by).offset(offset).limit(limit)
    result = await session.execute(query)
    documents = list(result.scalars().all())

    # 5. Repository -> Service
    return documents, total
