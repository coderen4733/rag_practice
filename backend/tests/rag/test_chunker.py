#  * 텍스트 추출(parser.py) + 청크 분할(chunker.py) 테스트
#  - API를 거치지 않고 "함수 자체"만 따로 테스트 (DB, Qdrant, 임베딩 서버 모두 필요 없음)
#    => 이런 테스트를 "단위 테스트(Unit Test)"라고 부름 (기능의 가장 작은 단위를 검사)

import pytest

from src.services.rag.document.chunker import split_text
from src.services.rag.document.parser import DocumentParseError, extract_text


# ─────────────────────────────────────────────
# 1. 텍스트 추출 (parser.extract_text)
# ─────────────────────────────────────────────
# 여러 인코딩(글자 저장 방식)으로 저장된 파일을 모두 똑같은 글자로 읽어야 함
#  - @pytest.mark.parametrize("이름1,이름2", [(값1, 값2), ...]): 값 묶음마다 테스트를 한 번씩 실행
@pytest.mark.parametrize(
    "data",
    [
        "휴가 규정입니다.".encode(),  # UTF-8 (기본)
        "휴가 규정입니다.".encode("utf-8-sig"),  # UTF-8 + BOM (메모장에서 저장한 UTF-8)
        "휴가 규정입니다.".encode("cp949"),  # CP949 (한국어 Windows의 옛날 방식)
    ],
)
def test_extract_text_encodings(data):
    assert extract_text(data, ".txt") == "휴가 규정입니다."


# 텍스트 파일이 아닌 것(NUL 문자 포함)은 거절
def test_extract_text_binary_file():
    with pytest.raises(DocumentParseError, match="텍스트 파일이 아닙니다"):
        extract_text(b"\x89PNG\x00\x00\x00data", ".txt")


# 지원하지 않는 확장자는 거절
def test_extract_text_unsupported_extension():
    with pytest.raises(DocumentParseError, match="지원하지 않는"):
        extract_text(b"hello", ".pdf")


# ─────────────────────────────────────────────
# 2. 청크 분할 (chunker.split_text)
# ─────────────────────────────────────────────
# 내용이 없거나 공백만 있으면 => 빈 리스트
@pytest.mark.parametrize("text", ["", "   ", "\n\n\t  \n"])
def test_split_text_empty(text):
    assert split_text(text, chunk_size=500, chunk_overlap=100) == []


# 청크 크기보다 짧은 문서 => 앞뒤 공백만 제거된 청크 1개
def test_split_text_short_text():
    assert split_text("  짧은 문서입니다.  ", chunk_size=500, chunk_overlap=100) == [
        "짧은 문서입니다."
    ]


# 자연스러운 경계가 없으면 => 정확히 chunk_size에서 자르고, 다음 청크는 겹침 길이만큼 앞에서 시작
def test_split_text_hard_cut_with_overlap():
    chunks = split_text("가나다라마바사아자차카타파하", chunk_size=10, chunk_overlap=3)
    assert chunks == ["가나다라마바사아자차", "아자차카타파하"]


# 문단 경계(빈 줄)가 있으면 => 그 위치에서 우선적으로 자름
def test_split_text_prefers_paragraph_boundary():
    first = "첫 번째 문단입니다. " * 3  # 약 36자
    second = "두 번째 문단입니다. " * 3
    chunks = split_text(first.strip() + "\n\n" + second.strip(), chunk_size=60, chunk_overlap=5)
    # 첫 번째 청크는 첫 문단 전체로 끝나야 함 (두 번째 문단이 섞이지 않음)
    assert chunks[0] == first.strip()


# 긴 문서 => 모든 청크가 chunk_size 이하이고,
#           모든 문장이 어떤 청크에든 들어 있어야 함 (내용 손실 없음)
def test_split_text_long_document_keeps_all_content():
    sentences = [f"{number}번 규정은 매우 중요한 내용입니다." for number in range(200)]
    text = " ".join(sentences)

    chunks = split_text(text, chunk_size=500, chunk_overlap=100)

    assert len(chunks) > 1
    assert all(len(chunk) <= 500 for chunk in chunks)
    for sentence in sentences:
        assert any(sentence in chunk for chunk in chunks), f"누락된 문장: {sentence}"


# Windows 줄바꿈(\r\n)은 \n으로 통일
def test_split_text_normalizes_line_breaks():
    chunks = split_text("첫 줄\r\n둘째 줄", chunk_size=500, chunk_overlap=100)
    assert chunks == ["첫 줄\n둘째 줄"]


# 겹침이 청크 크기의 절반 이상이면 => ValueError
def test_split_text_invalid_overlap():
    with pytest.raises(ValueError):
        split_text("내용", chunk_size=100, chunk_overlap=50)
