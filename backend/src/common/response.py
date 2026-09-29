from pydantic import BaseModel


# Response Schema 정의
#  * Generic[T] 방식 -> 파이썬 3.12의 새로운 제네릭 문법 class 클래스명[T] 방식
#  - 예) class ResponseSchema[T](BaseModel):
#  - T: "들어올 데이터 타입을 나중에 정하겠다"는 의미의 타입 변수
#    예) ResponseSchema[UserCreateRes] => data 필드의 타입이 UserCreateRes가 됨
class ResponseSchema[T](BaseModel):
    message: str
    data: T | None = None
