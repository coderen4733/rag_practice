#  * 긴 텍스트를 여러 개의 청크(조각)로 자르는 기능
#  - 문서 전체를 chunk_size(기본 500자) 정도의 조각으로 나눔
#
# 📌 왜 문서를 잘라서 저장하는가?
#  - 문서 전체를 벡터 하나로 만들면 여러 주제가 섞여서 "어느 부분이 질문과 관련 있는지" 알 수 없음
#  - 작게 자르면 질문과 관련 있는 "부분"만 정확히 찾아서 LLM에게 전달할 수 있음
#
# 📌 자르는 방법 (슬라이딩 윈도우)
#  1) 현재 위치에서 chunk_size 글자만큼 창(window)을 잡음
#  2) 창의 뒤쪽 절반 안에서 "자연스러운 경계"(문단 > 줄바꿈 > 문장 끝 > 띄어쓰기)를 찾아
#     그 위치에서 자름
#     => 문장이나 단어 중간에서 잘리는 것을 최대한 피함
#  3) 다음 청크는 방금 자른 위치보다 chunk_overlap 글자 "앞"에서 시작 (앞 청크와 조금 겹침)
#     => 경계 부근의 문맥이 다음 청크에도 남아 있어서 의미가 끊기지 않음
#
#  예) chunk_size=10, chunk_overlap=3 이라면 (경계를 못 찾은 경우)
#      "가나다라마바사아자차카타파하" => ["가나다라마바사아자차", "아자차카타파하"]
#      => 뒤 청크는 "앞 청크의 끝 3글자(아자차)"부터 시작해서 겹침

# 청크를 자를 때 찾는 "자연스러운 경계" (앞에 있을수록 우선)
#  - "\n\n": 문단 사이 빈 줄 / "\n": 줄바꿈 / ". " "? " "! ": 문장 끝 / " ": 띄어쓰기
SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", " "]


# 텍스트를 청크 목록으로 자르기
#  - 사용법: chunks = split_text(문서내용, chunk_size=500, chunk_overlap=100)
#  - 반환값: 청크 문자열 목록 (내용이 없으면 빈 리스트)
def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    # 1. 설정값 확인 (config.py에서도 검사하지만, 이 함수만 따로 쓸 때를 위해 한 번 더 확인)
    #  - 겹침이 청크 크기의 절반 이상이면 청크가 조금씩만 앞으로 나아가서 개수가 폭발적으로 늘어남
    if chunk_overlap >= chunk_size // 2:
        raise ValueError("chunk_overlap은 chunk_size의 절반보다 작아야 합니다.")

    # 2. 줄바꿈 문자 통일 (Windows의 \r\n, 옛날 Mac의 \r => \n) + 앞뒤 공백 제거
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    # 3. 앞에서부터 차례로 청크 자르기
    chunks = []
    start = 0  # 현재 청크의 시작 위치
    length = len(text)
    while start < length:
        # 3-1. 창의 끝 위치 (문서 끝을 넘지 않도록 min 사용)
        end = min(start + chunk_size, length)
        # 3-2. 문서 끝이 아니면 자연스러운 경계에서 자르도록 끝 위치 조정
        if end < length:
            end = _find_cut_position(text, start, end, chunk_size)
        # 3-3. 청크 저장 (앞뒤 공백 제거, 공백만 있는 청크는 버림)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        # 3-4. 문서 끝까지 왔으면 종료
        if end >= length:
            break
        # 3-5. 다음 청크는 겹침 길이만큼 앞에서 시작
        start = end - chunk_overlap
    return chunks


# 창(start ~ end) 안에서 자르기 좋은 위치 찾기 (이 파일 안에서만 사용)
#  - 창의 "뒤쪽 절반"에서만 찾는 이유: 앞쪽에서 자르면 청크가 너무 짧아지기 때문
#  - 경계를 하나도 못 찾으면 원래 끝 위치(end)에서 그냥 자름
def _find_cut_position(text: str, start: int, end: int, chunk_size: int) -> int:
    min_end = start + chunk_size // 2
    for separator in SEPARATORS:
        # rfind(찾을글자, 시작, 끝): 범위 안에서 "가장 뒤에 있는" 위치를 찾음 (없으면 -1)
        position = text.rfind(separator, min_end, end)
        if position != -1:
            # 경계 문자까지 포함해서 자름 (예: 문장 끝의 ". " 까지 앞 청크에 포함)
            return position + len(separator)
    return end
