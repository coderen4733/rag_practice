# 함수 결과를 기억(캐시)해 두는 데코레이터(같은 호출이면 다시 계산하지 않음)
from functools import lru_cache

# 파일 경로를 다루기 위한 표준 라이브러리(.env에서 절대경로 계산용)
from pathlib import Path

#  * Field import (환경 변수 값의 길이 등 검증 규칙을 지정하기 위함)
#  - JWT 비밀키의 최소 길이(32자)를 검사하는 데 사용
#  * model_validator import
#  - 여러 설정값을 "함께" 비교하는 검사(청크 겹침 < 청크 크기의 절반)를 만들기 위해 사용
from pydantic import Field, model_validator

# pydantic_settings: 환경 변수를 읽어 파이썬 객체로 자동 변환/검증해 주는 라이브러리
from pydantic_settings import BaseSettings, SettingsConfigDict

#  * .env 파일 위치를 "이 파일(config.py) 기준 절대경로"로 계산
#  - Path(__file__)            => backend/src/core/config.py
#  - .resolve().parents[2]     => 위로 3단계 올라간 폴더 = backend/
#    (parents[0]=core, parents[1]=src, parents[2]=backend)
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE_PATH = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    # 설정 동작 방식 지정:
    #  - case_sensitive=False: 환경 변수 이름의 대소문자를 구분하지 않음
    #  - extra="ignore": .env에 더 많은 변수가 있어도 에러 내지 말고 무시
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=ENV_FILE_PATH,  # ".env" -> 절대경로(ENV_FILE_PATH)
        env_file_encoding="utf-8",
        extra="ignore",
        #  * 설정값 검사 에러 메시지에 .env의 값이 출력되지 않도록 설정 (보안)
        #  - 기존: 없음 => 필수값이 빠지면 에러 메시지에 .env에 적힌 다른 값들(비밀번호 등)까지
        #          함께 출력되어, 서버 로그나 화면에 비밀값이 남을 수 있었음
        #  - 변경: hide_input_in_errors=True => "어떤 설정이 잘못되었는지"만 출력하고 값은 숨김
        hide_input_in_errors=True,
    )

    # 저장소/외부 시스템 접속 주소
    #  .env에 DB_URL이 없으면 서버 시작 시 "db_url Field required" 라고 바로 알려줌
    db_url: str  # Database URL (Postgres DB 접속 주소) - 필수
    # redis_url은 아직 사용하는 코드가 없으므로 기본값("")을 유지
    # (실제로 연결 코드를 작성할 때 db_url처럼 기본값을 지워 필수값으로 바꾸면 됨)
    redis_url: str = ""  # Redis 접속 주소 (작업 큐 + 요청 제한 카운터)

    #  * Vector DB(Qdrant) 관련 설정 + vector_db_url을 필수값으로
    #    => .env에 VECTOR_DB_URL이 없으면 서버 시작 시 "vector_db_url Field required" 에러
    #  - 클라우드(Qdrant Cloud)든 고객사 자체 Qdrant든 .env 값만 바꾸면 전환 가능
    vector_db_url: str  # Qdrant 접속 주소 (예: https://xxx.cloud.qdrant.io:6333) - 필수
    # API 키: Qdrant Cloud는 필수, API 키를 설정하지 않은 자체 운영 Qdrant는 비워둠(None)
    vector_db_api_key: str | None = None
    # 문서 청크(벡터)를 저장할 컬렉션 이름 (컬렉션: Qdrant에서 테이블 같은 개념)
    vector_db_collection: str = "documents"
    vector_db_timeout: int = 10  # Qdrant 요청 제한 시간 (단위: 초)

    #  * 임베딩(Embedding) 서버 관련 설정
    #  - 임베딩은 앱 안에서 계산하지 않고, OpenAI 호환 API(/v1/embeddings)를 가진
    #          별도 서버에 요청해서 받아옴 (src/core/embedding.py)
    #    - 개발: Docker로 띄운 Ollama 컨테이너 (CPU) => http://localhost:8081/v1
    #    - 납품: 고객사 환경의 임베딩 서버 주소로 .env만 변경
    embedding_base_url: str  # 임베딩 서버 주소 (/v1 까지) - 필수
    # API 키: 인증이 필요한 임베딩 서버만 사용 (Ollama는 필요 없으므로 비워둠)
    embedding_api_key: str | None = None
    embedding_model: str = "bge-m3"  # 임베딩 모델 이름 (임베딩 서버에 등록된 이름)
    # 벡터 차원: 모델이 만들어내는 숫자 목록의 길이 (bge-m3 = 1024)
    #  - ⚠️ Qdrant 컬렉션을 이 차원으로 만들기 때문에, 모델을 바꾸면 이 값도 반드시 같이 바꿔야 함
    embedding_dim: int = 1024
    # 한 번의 요청에 보낼 문장 수 (문서 청크가 많을 때 나눠서 보냄)
    embedding_batch_size: int = 32
    embedding_timeout: int = 60  # 임베딩 요청 제한 시간 (단위: 초, CPU는 느릴 수 있어 넉넉하게)

    #  * 문서 등록(업로드 -> 청크 분할) 관련
    #  - 업로드 파일 크기 제한, 청크 크기, 청크 겹침 길이를 환경 변수로 조절
    #  - 파일 크기 제한 (단위: 바이트, 기본값 1MB = 1024 * 1024)
    #    => 지금은 업로드 요청 안에서 바로 임베딩까지 처리하므로, 파일이 크면 요청이 너무 오래 걸림
    #       (1MB ≒ 한글 약 35만 자 ≒ 청크 약 900개)
    #    => 나중에 Celery 백그라운드 처리를 추가하면 늘릴 수 있음
    document_max_file_size: int = Field(default=1024 * 1024, ge=1)
    # 청크 크기 (단위: 글자 수) - 문서를 이 길이 정도로 잘라서 각각 임베딩
    #  - 너무 크면: 여러 주제가 한 청크에 섞여서 검색이 부정확해짐
    #  - 너무 작으면: 문맥이 끊겨서 청크 하나만 보고는 의미를 알기 어려움
    document_chunk_size: int = Field(default=500, ge=100)
    # 청크 겹침 길이 (단위: 글자 수) - 앞 청크의 끝부분을 다음 청크 앞에 다시 넣음
    #  => 문장이 청크 경계에서 잘려도, 다음 청크에 앞 내용이 조금 남아 있어 문맥이 이어짐
    document_chunk_overlap: int = Field(default=100, ge=0)

    #  * LLM(답변 생성 AI) 서버 관련
    #  - LLM은 앱 안에서 실행하지 않고, OpenAI 호환 API(/v1/chat/completions)를 가진
    #    별도 서버에 요청해서 답변을 받아옴 (src/core/llm.py)
    #    - 개발: 맥북에 설치한 Ollama 앱 (GPU) => http://localhost:11434/v1
    #    - 납품: 고객사 GPU 서버(vLLM 등) 주소로 .env만 변경
    llm_base_url: str  # LLM 서버 주소 (/v1 까지) - 필수
    # API 키: 인증이 필요한 LLM 서버만 사용 (Ollama는 필요 없으므로 비워둠)
    llm_api_key: str | None = None
    llm_model: str = "qwen3.5:9b"  # LLM 모델 이름 (LLM 서버에 등록된 이름)
    # 답변 생성 제한 시간 (단위: 초) - 긴 답변을 생성할 수 있으므로 넉넉하게
    llm_timeout: int = 180
    # 창의성 (0 ~ 2): 낮을수록 같은 질문에 비슷한 답, 높을수록 다양한 답
    #  - 회사 문서를 근거로 정확하게 답해야 하므로 낮게 설정
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    # 답변 최대 길이 (단위: 토큰, 한글 1글자 ≒ 1~2토큰)
    llm_max_tokens: int = Field(default=1024, ge=1)
    # 생각 모드(thinking) 조절값 - OpenAI 호환 API의 reasoning_effort 값으로 전달
    #  - Qwen3.5 같은 모델은 답하기 전에 "생각"을 길게 생성해서 답변이 매우 느려짐
    #    (실측: 생각 모드 켜짐 11.5초 / "none"으로 끄면 0.2초)
    #  - Ollama는 "none"으로 생각 모드가 꺼짐. 비워두면(None) 이 값을 보내지 않음
    llm_reasoning_effort: str | None = "none"
    # LLM 서버에 함께 보낼 추가 설정 (JSON 형식) - LLM 서버 종류마다 다른 옵션을 넣을 때 사용
    #  - 예) vLLM에서 Qwen 생각 모드 끄기:
    #        LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}
    llm_extra_body: dict = {}

    #  * 챗봇(문서 근거 답변) 관련 설정
    #  - 답변의 근거로 LLM에게 넘길 검색 결과(청크) 개수
    #    => 많을수록 정보는 많지만, 관련 없는 내용이 섞이고 답변이 느려짐
    #    => 검색 품질 평가에서 상위 5개 안에 정답 문서가 100% 들어 있었으므로 기본값 5
    chat_top_k: int = Field(default=5, ge=1, le=20)
    #  * 대화 이어가기 설정
    #  - 이전 대화를 참고해서 이어서 묻는 질문에도 답할 수 있게 함
    # 이전 대화 중 LLM에게 함께 보낼 최근 메시지 수 (질문 1개 + 답변 1개 = 2개)
    #  - 많을수록 오래전 대화도 기억하지만, LLM이 읽을 글이 늘어나 답변이 느려짐
    #  - 0이면 이전 대화를 보내지 않음 (기존처럼 질문마다 따로 답함)
    chat_history_messages: int = Field(default=6, ge=0, le=20)
    # 이어서 묻는 질문을 검색 전에 "혼자서도 뜻이 통하는 질문"으로 다시 쓸지 여부
    #  - 예) "그럼 신입사원은?" => "신입사원의 연차는 며칠인가?" 로 다시 쓴 뒤 검색
    #  - LLM을 한 번 더 호출하므로 이어서 묻는 질문은 1~2초 정도 느려짐 (첫 질문은 영향 없음)
    chat_query_rewrite: bool = True

    #  * 청크 설정값 검사
    #  - 청크 겹침이 청크 크기의 절반 이상이면 서버 시작 시 에러
    #    => 겹침이 너무 크면 청크가 조금씩만 앞으로 나아가서 청크 개수가 폭발적으로 늘어남
    #  - @model_validator(mode="after"): 모든 설정값을 읽은 "후"에 실행되는 검사 함수
    @model_validator(mode="after")
    def check_chunk_settings(self) -> "Settings":
        if self.document_chunk_overlap >= self.document_chunk_size // 2:
            raise ValueError(
                "DOCUMENT_CHUNK_OVERLAP은 DOCUMENT_CHUNK_SIZE의 절반보다 작아야 합니다."
            )
        return self

    #  * DB에서 실행되는 SQL을 콘솔에 출력할지 여부를 환경 변수로 제어
    #  - 기본값은 False(출력 안 함), 개발 중 보고 싶으면 .env에 DB_ECHO=true 추가
    db_echo: bool = False

    #  * CORS 허용 도메인 목록을 환경 변수로 관리
    #  - 기존: main.py에 allow_origins=["*"](모든 사이트 허용)가 하드코딩되어 있었음
    #  - 변경: 여기에 적힌 주소(프론트엔드 주소)에서 온 요청만 허용
    #  - .env 작성 예시(JSON 배열 형식): CORS_ORIGINS=["http://localhost:3000","https://my-app.com"]
    #  - .env에 값이 없으면 아래 기본값(로컬 프론트엔드 개발 서버 주소)을 사용
    cors_origins: list[str] = ["http://localhost:3000"]

    # JWT 관련
    jwt_algorithm: str = "HS256"  # 토큰 서명 알고리즘 (HS256: 비밀키 하나로 서명/검증)
    access_token_secret: str = Field(min_length=32)
    refresh_token_secret: str = Field(min_length=32)
    access_token_expire: int = 30  # 액세스 토큰 유효기간 (단위: 분)
    refresh_token_expire: int = 1  # 리프레시 토큰 유효기간 (단위: 일)

    #  * psycopg 드라이버용 DB 주소를 만들어 주는 속성(property)
    #  - 한 곳(여기)에 모아두고 database.py, env.py 모두 settings.async_db_url을 사용
    #  - @property: 함수지만 괄호 없이 settings.async_db_url 처럼 변수처럼 꺼내 쓸 수 있게 해줌
    @property
    def async_db_url(self) -> str:
        # Supabase가 주는 주소는 "postgresql://..." 형태
        # SQLAlchemy가 psycopg(3버전) 드라이버를 사용하려면 "postgresql+psycopg://..." 이어야 함
        if self.db_url.startswith("postgresql://"):
            return self.db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.db_url


# @lru_cache를 붙였으므로 get_settings()는 처음 한 번만 Settings() 를 만들고,
# 그 뒤로는 같은 객체를 재사용(환경 변수를 매번 다시 읽지 않아 빠르고 일관적)
@lru_cache
def get_settings() -> Settings:
    return Settings()
