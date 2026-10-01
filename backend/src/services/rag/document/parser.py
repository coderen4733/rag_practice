#  * 업로드된 파일에서 텍스트를 꺼내는 기능
#  - 파일(바이트)을 읽어서 문자열(텍스트)로 바꿈
#  - 지금은 .txt, .md 만 지원 (둘 다 "글자만 있는 파일"이라 읽는 방법이 같음)
#  - ⚠️ 나중에 PDF를 지원하려면 이 파일에 PDF 읽는 코드를 추가하고,
#    SUPPORTED_EXTENSIONS에 ".pdf"를 추가하면 됨 (다른 파일은 수정할 필요 없음)

# 지원하는 파일 확장자 목록 (소문자)
SUPPORTED_EXTENSIONS = {".txt", ".md"}

# 텍스트 파일을 읽을 때 시도할 인코딩(글자 저장 방식) 순서
#  - utf-8-sig: 요즘 대부분의 파일이 쓰는 UTF-8 (맨 앞의 BOM 표시가 있으면 자동으로 제거)
#  - cp949    : 한국어 Windows(메모장 등)에서 저장한 옛날 파일이 많이 쓰는 방식
#  => UTF-8로 먼저 읽어보고, 실패하면 CP949로 다시 시도
TEXT_ENCODINGS = ("utf-8-sig", "cp949")


# 문서 파일을 읽을 수 없을 때 발생하는 에러
class DocumentParseError(Exception):
    pass


# 파일 내용(바이트)에서 텍스트 꺼내기
#  - data: 파일 내용 (bytes), extension: 확장자 (예: ".md")
def extract_text(data: bytes, extension: str) -> str:
    # 1. 지원하는 형식인지 확인
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentParseError(f"지원하지 않는 파일 형식입니다. ({extension})")
    # 2. .txt, .md => 텍스트 파일로 읽기
    return _decode_text(data)


# 바이트를 문자열로 바꾸기 (여러 인코딩을 차례로 시도)
def _decode_text(data: bytes) -> str:
    for encoding in TEXT_ENCODINGS:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            # 이 인코딩으로 읽을 수 없으면 다음 인코딩으로 다시 시도
            continue
        # NUL 문자(\x00)가 있으면 글자 파일이 아니라 이미지/실행 파일 등을
        # 확장자만 .txt로 바꾼 것일 가능성이 높으므로 거절
        if "\x00" in text:
            raise DocumentParseError("텍스트 파일이 아닙니다.")
        return text
    raise DocumentParseError("파일의 글자 인코딩을 읽을 수 없습니다. (UTF-8 또는 CP949만 지원)")
