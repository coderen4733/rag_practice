#  * 모든 SQLAlchemy 모델(테이블)이 공통으로 상속받을 Base 클래스를 모아둔 파일
#  - 기존: Base가 src/services/iam/user/model.py 안에 정의되어 있었음
#    => 앞으로 문서(Document), 에이전트(Agent) 등 모델이 늘어날 때 각자 Base를 만들면
#       테이블 정보가 여러 곳에 흩어져 alembic이 모든 테이블을 한 번에 인식하지 못함
#  - 변경: Base를 core에 하나만 두고, 모든 모델이 이 Base를 import 해서 상속
#    => 모든 테이블 정보가 Base.metadata 한 곳에 모이고, alembic은 이것만 보면 됨

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncAttrs  # 비동기 환경에서 관계(relationship) 로딩 지원
from sqlalchemy.orm import DeclarativeBase  # SQLAlchemy 2.0 방식의 모델 기본 클래스

# 사용할 스키마 선택
#  * 스키마 이름을 이 한 곳에서만 관리
#  - 스키마: DB 안의 "폴더" 같은 개념 (Supabase 기본 스키마는 public)
TARGET_SCHEMA = "rag_practice"


class Base(AsyncAttrs, DeclarativeBase):
    # metadata: 이 Base를 상속한 모든 테이블 정보가 저장되는 곳
    # MetaData(schema=TARGET_SCHEMA)
    #  => 이 Base를 상속한 모든 테이블은 자동으로 rag_practice 스키마에 만들어짐
    #  => 모델마다 __table_args__ = {"schema": "rag_practice"} 를 적지 않아도 됨
    metadata = MetaData(schema=TARGET_SCHEMA)
