#  * 여러 테스트 파일에서 함께 쓰는 상수 모음
#  - 테스트용 사용자의 기본 비밀번호 등을 한 곳에서 관리
#  - conftest.py에 두지 않은 이유: conftest.py는 pytest가 자동으로 읽는 특별한 파일이라,
#    테스트 파일에서 "from tests.conftest import ..." 처럼 직접 import 하는 것은 권장되지 않음

# 테스트용 사용자의 기본 비밀번호 (make_user로 만든 모든 사용자는 이 비밀번호를 가짐)
TEST_PASSWORD = "password123"
