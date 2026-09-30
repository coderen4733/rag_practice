#  * 새 파일 추가 - 문서(Document) 등록/조회/삭제 로직
#  - 문서 업로드 -> 텍스트 추출 -> 청크 분할 -> 임베딩 -> Qdrant 저장 흐름을 담당
#
# 📌 문서 등록 전체 흐름 (upload_document)
#  1) 파일 검사 (이름, 확장자, 크기)
#  2) 텍스트 추출 + 청크 분할
#  3) DB에 "처리 중(processing)" 상태로 문서 정보 저장
#  4) 청크를 임베딩해서 Qdrant에 저장
#  5) 성공 => "완료(completed)" / 실패 => "실패(failed)" 로 상태 변경

import logging
import math
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

# embedding, vector_db를 "파일(모듈)째로" import 하는 이유:
#  - embedding.embed_texts(...) 처럼 호출하면, 테스트에서 이 함수를 가짜로 바꿔치기하기 쉬움
from src.core import embedding, vector_db
from src.core.config import get_settings
from src.services.iam.user.models import User
from src.services.rag.document import chunker, parser
from src.services.rag.document import repository as document_repository
from src.services.rag.document.enums import DocumentStatus
from src.services.rag.document.models import Document
from src.services.rag.document.schemas import (
    DocumentDeleteRes,
    DocumentReadListQuery,
    DocumentReadListRes,
    DocumentRes,
)

# __name__: 현재 파일의 모듈 이름으로 로거를 만들어, 로그가 어디서 나왔는지 표시
logger = logging.getLogger(__name__)

# get_settings()를 호출하여 환경변수 객체 가져오기 (파일 크기 제한, 청크 크기 등)
settings = get_settings()


# 문서(Document) 등록(C) API
#  - current_user: 업로드한 관리자 (라우터의 AdminOrManagerUser가 넘겨줌)
async def upload_document(
    session: AsyncSession,
    file: UploadFile,
    current_user: User,
) -> DocumentRes:
    # 1. 파일 검사
    # 1-1. 파일 이름 확인
    #  - Path(...).name: 경로를 제외한 "파일 이름"만 꺼냄 (예: "../../a.txt" => "a.txt")
    #    => 파일 이름에 경로를 넣어 보내는 공격을 막음
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="파일 이름이 없습니다.",
        )
    if len(filename) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="파일 이름은 255자 이하여야 합니다.",
        )
    # 1-2. 확장자 확인 (대소문자 구분 없이: .MD => .md)
    #  - 415(Unsupported Media Type): "지원하지 않는 형식의 파일"이라는 뜻의 HTTP 상태 코드
    file_extension = Path(filename).suffix.lower()
    if file_extension not in parser.SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(parser.SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"지원하지 않는 파일 형식입니다. ({allowed} 만 가능)",
        )
    # 1-3. 크기 확인
    #  - 제한보다 "1바이트 더" 읽어봄 => 1바이트라도 더 읽히면 제한 초과
    #    (파일 전체를 다 읽지 않고도 초과 여부를 알 수 있어서, 아주 큰 파일에도 안전)
    #  - 413(Content Too Large): "보낸 데이터가 너무 크다"는 뜻의 HTTP 상태 코드
    max_size = settings.document_max_file_size
    data = await file.read(max_size + 1)
    if len(data) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"파일 크기는 {max_size:,}바이트 이하여야 합니다.",
        )

    # 2. 텍스트 추출 + 청크 분할
    try:
        text = parser.extract_text(data, file_extension)
    except parser.DocumentParseError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    chunks = chunker.split_text(
        text,
        chunk_size=settings.document_chunk_size,
        chunk_overlap=settings.document_chunk_overlap,
    )
    # 빈 파일이거나 공백만 있는 파일
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="내용이 없는 문서입니다.",
        )

    # 3. DB에 "처리 중" 상태로 문서 정보 저장
    #  - 임베딩 전에 먼저 저장(commit)하는 이유:
    #    Qdrant에 저장할 청크에 "문서 id"를 넣어야 하는데, id는 DB에 저장해야 발급됨
    document = Document(
        filename=filename,
        file_extension=file_extension,
        file_size=len(data),
        status=DocumentStatus.PROCESSING,
        uploaded_by=current_user.id,
    )
    document = await document_repository.create_document(session, document)
    await session.commit()

    # 4. 청크를 임베딩해서 Qdrant에 저장
    try:
        await _index_chunks(document, chunks)
    except (embedding.EmbeddingError, vector_db.VectorDBError) as err:
        # 4-F. 실패 처리
        await _mark_as_failed(session, document, err)
        #  - 503(Service Unavailable): "서버가 일시적으로 요청을 처리할 수 없다"는 뜻
        #    (우리 서버가 아니라 임베딩 서버나 Vector DB에 문제가 생긴 상황)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=document.error_message,
        ) from err

    # 5. "완료" 상태로 변경
    document.status = DocumentStatus.COMPLETED
    document.chunk_count = len(chunks)
    document = await document_repository.update_document(session, document)
    await session.commit()

    # 6. SQLAlchemy 객체 -> Pydantic Response 모델 변환
    data = DocumentRes.model_validate(document)
    # 7. Service -> Router
    return data


# 청크를 임베딩해서 Qdrant에 저장 (이 파일 안에서만 사용)
#  - 청크를 embedding_batch_size(기본 32개)씩 나눠서 "임베딩 -> 저장"을 반복
#    => 청크 수백 개의 벡터를 한 번에 메모리에 올리지 않아도 됨
async def _index_chunks(document: Document, chunks: list[str]) -> None:
    batch_size = settings.embedding_batch_size
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        # 1. 청크들을 벡터로 변환 (임베딩 서버 호출)
        vectors = await embedding.embed_texts(batch)
        # 2. 청크 원문 + 벡터를 Qdrant에 저장
        #  - start_index=start: 청크 번호가 0, 1, 2 ... 로 끝까지 이어지도록
        await vector_db.upsert_document_chunks(
            document_id=document.id,
            filename=document.filename,
            chunks=batch,
            vectors=vectors,
            start_index=start,
        )


# 문서 처리 실패 시 뒷정리 (이 파일 안에서만 사용)
#  - 1) 중간까지 저장된 청크 삭제 (예: 100개 중 64개까지 저장 후 실패한 경우)
#  - 2) 문서 상태를 "실패"로 바꾸고 실패 이유 저장
async def _mark_as_failed(session: AsyncSession, document: Document, err: Exception) -> None:
    # 1. 자세한 에러 내용은 서버 로그에만 남김
    #  - 에러 내용에는 서버 주소 등 내부 정보가 들어 있을 수 있어서 사용자에게는 보여주지 않음
    logger.error(f"🔴 문서 처리 실패 (document_id={document.id}): {err!r}")
    # 2. 중간까지 저장된 청크 삭제 (삭제도 실패하면 로그만 남기고 넘어감)
    try:
        await vector_db.delete_document_chunks(document.id)
    except vector_db.VectorDBError as cleanup_err:
        logger.error(
            f"🔴 실패한 문서의 청크 정리 실패 (document_id={document.id}): {cleanup_err!r}"
        )
    # 3. 상태를 "실패"로 변경하고 사용자에게 보여줄 실패 이유 저장
    if isinstance(err, embedding.EmbeddingError):
        document.error_message = "임베딩 서버에 문제가 있어 문서를 처리하지 못했습니다."
    else:
        document.error_message = "Vector DB에 문제가 있어 문서를 처리하지 못했습니다."
    document.status = DocumentStatus.FAILED
    await document_repository.update_document(session, document)
    await session.commit()


# 문서(Document) 조회(R-D) API
async def read_document(
    session: AsyncSession,
    document_id: int,
) -> DocumentRes:
    # 1. 문서 조회 (없으면 404)
    document = await _get_document_or_404(session, document_id)
    # 2. SQLAlchemy 객체 -> Pydantic Response 모델 변환
    data = DocumentRes.model_validate(document)
    # 3. Service -> Router
    return data


# 문서(Document) 목록 조회(R-L) API
#  - user/service.py의 read_users_list와 같은 방식
async def read_documents_list(
    session: AsyncSession,
    query: DocumentReadListQuery,
) -> DocumentReadListRes:
    # 1. 페이지 번호 -> 건너뛸 개수(offset) 계산
    offset = (query.page - 1) * query.size
    # 2. 파일명 검색어 정리 (공백만 입력한 경우는 검색 안 함)
    filename_keyword = None
    if query.filename:
        filename_keyword = query.filename.strip() or None
    # 3. Service -> Repository
    documents, total = await document_repository.get_documents_list(
        session,
        status=query.status,
        filename=filename_keyword,
        order=query.order,
        offset=offset,
        limit=query.size,
    )
    # 4. 전체 페이지 수 계산
    total_pages = math.ceil(total / query.size)
    # 5. SQLAlchemy 객체 목록 -> Pydantic Response 모델 변환
    data = DocumentReadListRes(
        items=[DocumentRes.model_validate(document) for document in documents],
        total=total,
        page=query.page,
        size=query.size,
        total_pages=total_pages,
    )
    # 6. Service -> Router
    return data


# 문서(Document) 삭제(D) API
#  - Qdrant의 청크를 먼저 지우고, 그 다음 DB의 문서 정보를 지움
#    => 순서를 반대로 하면, Qdrant 삭제가 실패했을 때 "DB에는 없는데 검색은 되는" 청크가 남음
#    => 이 순서면 Qdrant 삭제 실패 시 DB 정보가 남아 있으므로 나중에 다시 삭제할 수 있음
async def delete_document(
    session: AsyncSession,
    document_id: int,
) -> DocumentDeleteRes:
    # 1. 문서 조회 (없으면 404)
    document = await _get_document_or_404(session, document_id)
    # 2. Qdrant에서 이 문서의 청크 전부 삭제
    try:
        await vector_db.delete_document_chunks(document.id)
    except vector_db.VectorDBError as err:
        logger.error(f"🔴 문서 청크 삭제 실패 (document_id={document.id}): {err!r}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector DB에 문제가 있어 문서를 삭제하지 못했습니다.",
        ) from err
    # 3. DB에서 문서 정보 삭제
    # 3-1. Service -> Repository
    await document_repository.delete_document(session, document)
    # 3-2. 삭제 확정(commit)
    await session.commit()
    # 4. 데이터
    data = DocumentDeleteRes(
        success=True,
        id=document_id,
    )
    # 5. Service -> Router
    return data


# 문서 조회 + 없으면 404 (이 파일 안에서만 사용)
async def _get_document_or_404(session: AsyncSession, document_id: int) -> Document:
    document = await document_repository.get_document_by_id(session, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="존재하지 않는 문서입니다.",
        )
    return document
