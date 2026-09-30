# 함수 결과를 기억(캐시)해 두는 데코레이터(같은 호출이면 다시 계산하지 않음)
from functools import lru_cache

# 파일 경로를 다루기 위한 표준 라이브러리(.env에서 절대경로 계산용)
from pathlib import Path

#  * Field import 추가 (환경 변수 값의 길이 등 검증 규칙을 지정하기 위함)
#  - JWT 비밀키의 최소 길이(32자)를 검사하는 데 사용
from pydantic import Field

# pydantic_settings: 환경 변수를 읽어 파이썬 객체로 자동 변환/검증해 주는 라이브러리
from pydantic_settings import BaseSettings, SettingsConfigDict

#  * .env 파일 위치를 "이 파일(config.py) 기준 절대경로"로 계산
#  - 기존: env_file=".env" => "명령어를 실행한 위치" 기준으로 .env를 찾음
#    => backend/ 가 아닌 다른 폴더(IDE 디버거, Docker 등)에서 실행하면 .env를 못 찾는 문제
#  - 변경: 실행 위치와 상관없이 항상 backend/.env 를 찾음
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
    )

    # 저장소/외부 시스템 접속 주소
    #  * db_url의 기본값("")을 제거하여 "필수값"으로 변경
    #  - 기존: .env에 DB_URL이 없으면 빈 문자열("")이 들어가고,
    #          엔진 생성 시 "Could not parse SQLAlchemy URL" 이라는 알기 어려운 에러 발생
    #  - 변경: .env에 DB_URL이 없으면 서버 시작 시 "db_url Field required" 라고 바로 알려줌
    db_url: str  # Database URL (Postgres DB 접속 주소) - 필수
    # redis_url은 아직 사용하는 코드가 없으므로 기본값("")을 유지
    # (실제로 연결 코드를 작성할 때 db_url처럼 기본값을 지워 필수값으로 바꾸면 됨)
    redis_url: str = ""  # Redis 접속 주소 (작업 큐 + 요청 제한 카운터)

    #  * Vector DB(Qdrant) 관련 설정 추가 + vector_db_url을 필수값으로 변경
    #  - src/core/vector_db.py에서 실제로 연결하므로 기본값을 지워 필수값으로 변경
    #    => .env에 VECTOR_DB_URL이 없으면 서버 시작 시 "vector_db_url Field required" 에러
    #  - 클라우드(Qdrant Cloud)든 고객사 자체 Qdrant든 .env 값만 바꾸면 전환 가능
    vector_db_url: str  # Qdrant 접속 주소 (예: https://xxx.cloud.qdrant.io:6333) - 필수
    # API 키: Qdrant Cloud는 필수, API 키를 설정하지 않은 자체 운영 Qdrant는 비워둠(None)
    vector_db_api_key: str | None = None
    # 문서 청크(벡터)를 저장할 컬렉션 이름 (컬렉션: Qdrant에서 테이블 같은 개념)
    vector_db_collection: str = "documents"
    vector_db_timeout: int = 10  # Qdrant 요청 제한 시간 (단위: 초)

    #  * 임베딩(Embedding) 서버 관련 설정 추가
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

    #  * DB에서 실행되는 SQL을 콘솔에 출력할지 여부를 환경 변수로 제어
    #  - 기존: database.py에 echo=True가 하드코딩되어 운영 환경에서도 모든 SQL이 출력됨
    #  - 변경: 기본값은 False(출력 안 함), 개발 중 보고 싶으면 .env에 DB_ECHO=true 추가
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

    #  * psycopg 드라이버용 DB 주소를 만들어 주는 속성(property) 추가
    #  - 기존: database.py 안에서 주소 변환 코드를 직접 작성 => alembic(env.py)에서도 같은 코드 필요
    #  - 변경: 한 곳(여기)에 모아두고 database.py, env.py 모두 settings.async_db_url을 사용
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
