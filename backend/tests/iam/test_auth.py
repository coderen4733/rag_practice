#  * 인증(auth) API 테스트
#  - 회원가입 / 로그인 / 로그아웃 / 토큰재발급 / 비밀번호 변경의 동작을 코드로 저장
#    => uv run pytest 한 번으로 전부 다시 확인 가능
#
# 📌 테스트 함수 작성 규칙
#  - 함수 이름은 반드시 test_ 로 시작 (pytest가 이 이름으로 테스트를 찾음)
#  - 하나의 테스트는 "준비(Arrange) -> 실행(Act) -> 검증(Assert)" 3단계로 작성
#  - assert 조건: 조건이 거짓이면 테스트 실패(FAILED)로 표시됨
#  - 매개변수(client, make_user 등)는 conftest.py의 fixture가 자동으로 채워줌

from sqlalchemy import func, select, update

from src.core.security import hash_token
from src.services.iam.auth.models import RefreshToken
from src.services.iam.user.enums import UserRole
from src.services.iam.user.models import User
from tests.constants import TEST_PASSWORD


# ─────────────────────────────────────────────
# 테스트 도우미 함수 (여러 테스트에서 반복되는 코드를 줄이기 위함)
# ─────────────────────────────────────────────
# 로그인 API 호출
async def sign_in(client, email, password=TEST_PASSWORD):
    return await client.post("/auth/sign-in", json={"email": email, "password": password})


# 특정 사용자의 리프레시 토큰이 DB에 몇 개 저장되어 있는지 세기 (= 로그인된 기기 수)
async def count_refresh_tokens(session_factory, user_id):
    async with session_factory() as session:
        query = (
            select(func.count()).select_from(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        return await session.scalar(query)


# ─────────────────────────────────────────────
# 1. 회원가입 (POST /auth/sign-up)
# ─────────────────────────────────────────────
# 회원가입 성공 => 일반 사용자(user) + 승인 대기(is_active=False)로 생성되어야 함
async def test_sign_up_success(client):
    # 1. 준비: 요청 데이터 (email에 대문자 포함)
    body = {"email": "New@Corp.com", "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD}
    # 2. 실행
    response = await client.post("/auth/sign-up", json=body)
    # 3. 검증
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["email"] == "new@corp.com"  # 소문자로 저장되어야 함
    assert data["role"] == "user"
    assert data["is_active"] is False
    assert "hashed_password" not in data  # 비밀번호 해시는 절대 응답하면 안 됨


# 요청에 role=admin을 몰래 끼워 넣어도 무시되고 user로 생성되어야 함 (보안)
async def test_sign_up_ignores_role_field(client):
    body = {
        "email": "hacker@corp.com",
        "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD,
        "role": "admin",
    }
    response = await client.post("/auth/sign-up", json=body)
    assert response.status_code == 201
    assert response.json()["data"]["role"] == "user"


# 비밀번호와 비밀번호 확인이 다르면 400
async def test_sign_up_password_mismatch(client):
    body = {"email": "a@corp.com", "password": TEST_PASSWORD, "password_confirm": "different123"}
    response = await client.post("/auth/sign-up", json=body)
    assert response.status_code == 400


# 이미 있는 email이면 409 (대소문자만 다른 email도 같은 email로 취급)
async def test_sign_up_duplicate_email(client, make_user):
    # 1. 준비: 이미 가입된 사용자
    await make_user("dup@corp.com")
    # 2. 실행: 대문자로 같은 email 가입 시도
    body = {"email": "DUP@corp.com", "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD}
    response = await client.post("/auth/sign-up", json=body)
    # 3. 검증
    assert response.status_code == 409


# email이 50자를 넘으면 422 (DB 컬럼 길이 제한)
async def test_sign_up_email_too_long(client):
    long_email = "a" * 45 + "@corp.com"  # 54자
    body = {"email": long_email, "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD}
    response = await client.post("/auth/sign-up", json=body)
    assert response.status_code == 422


# ─────────────────────────────────────────────
# 2. 로그인 (POST /auth/sign-in)
# ─────────────────────────────────────────────
# 로그인 성공 => 토큰 2개 발급 + 리프레시 토큰은 "해시값"으로 DB에 저장되어야 함
async def test_sign_in_success(client, make_user, session_factory):
    user = await make_user("me@corp.com")

    response = await sign_in(client, "me@corp.com")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]
    # DB에는 토큰 원본이 아니라 해시값이 저장되어야 함
    async with session_factory() as session:
        saved = await session.get(RefreshToken, hash_token(data["refresh_token"]))
    assert saved is not None
    assert saved.user_id == user.id
    assert saved.hashed_token != data["refresh_token"]


# email 대소문자가 달라도 로그인 가능해야 함
async def test_sign_in_email_case_insensitive(client, make_user):
    await make_user("me@corp.com")
    response = await sign_in(client, "ME@Corp.com")
    assert response.status_code == 200


# 비밀번호가 틀린 경우와 없는 email인 경우 => 둘 다 401 + "같은 메시지"
#  - 메시지가 다르면 "이 email은 가입되어 있다"는 정보가 새어 나감
async def test_sign_in_fail_does_not_reveal_email(client, make_user):
    await make_user("me@corp.com")

    wrong_password = await sign_in(client, "me@corp.com", password="wrongpass1")
    unknown_email = await sign_in(client, "nobody@corp.com")

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


# 관리자 승인 전(is_active=False) 계정은 403
async def test_sign_in_inactive_user(client, make_user):
    await make_user("wait@corp.com", is_active=False)
    response = await sign_in(client, "wait@corp.com")
    assert response.status_code == 403


# ─────────────────────────────────────────────
# 3. 로그아웃 (POST /auth/sign-out)
# ─────────────────────────────────────────────
# 로그아웃 성공 => 같은 토큰으로 다시 로그아웃하거나 재발급하면 401
async def test_sign_out_success(client, make_user):
    await make_user("me@corp.com")
    refresh_token = (await sign_in(client, "me@corp.com")).json()["data"]["refresh_token"]

    response = await client.post("/auth/sign-out", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    # 이미 로그아웃한 토큰은 더 이상 사용할 수 없어야 함
    again = await client.post("/auth/sign-out", json={"refresh_token": refresh_token})
    assert again.status_code == 401
    re_token = await client.post("/auth/re-token", json={"refresh_token": refresh_token})
    assert re_token.status_code == 401


# DB에 없는 토큰으로 로그아웃하면 401
async def test_sign_out_unknown_token(client):
    response = await client.post("/auth/sign-out", json={"refresh_token": "unknown-token"})
    assert response.status_code == 401


# ─────────────────────────────────────────────
# 4. 토큰재발급 (POST /auth/re-token)
# ─────────────────────────────────────────────
# 재발급 성공 => 새 액세스 토큰으로 로그인이 필요한 API를 사용할 수 있어야 함
async def test_re_token_success(client, make_user):
    await make_user("me@corp.com")
    refresh_token = (await sign_in(client, "me@corp.com")).json()["data"]["refresh_token"]

    response = await client.post("/auth/re-token", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    new_access_token = response.json()["data"]["access_token"]
    me = await client.get("/users/me", headers={"Authorization": f"Bearer {new_access_token}"})
    assert me.status_code == 200


# 리프레시 토큰 자리에 액세스 토큰을 넣으면 401 (토큰 종류 검사)
async def test_re_token_with_access_token(client, make_user):
    await make_user("me@corp.com")
    access_token = (await sign_in(client, "me@corp.com")).json()["data"]["access_token"]

    response = await client.post("/auth/re-token", json={"refresh_token": access_token})

    assert response.status_code == 401


# 위조된(엉터리) 토큰이면 401
async def test_re_token_with_forged_token(client):
    response = await client.post("/auth/re-token", json={"refresh_token": "abc.def.ghi"})
    assert response.status_code == 401


# 토큰 발급 후 계정이 비활성화되면 재발급 불가 (401)
async def test_re_token_after_deactivated(client, make_user, session_factory):
    user = await make_user("me@corp.com")
    refresh_token = (await sign_in(client, "me@corp.com")).json()["data"]["refresh_token"]
    # 로그인 이후 관리자가 계정을 비활성화한 상황을 DB에서 직접 만듦
    async with session_factory() as session:
        await session.execute(update(User).where(User.id == user.id).values(is_active=False))
        await session.commit()

    response = await client.post("/auth/re-token", json={"refresh_token": refresh_token})

    assert response.status_code == 401


# ─────────────────────────────────────────────
# 5. 비밀번호 변경 (PATCH /auth/password)
# ─────────────────────────────────────────────
# 비밀번호 변경 요청 본문을 만드는 도우미 함수
def password_body(current=TEST_PASSWORD, new="newpass123", confirm=None):
    return {
        "current_password": current,
        "new_password": new,
        "new_password_confirm": confirm or new,
    }


# 비밀번호 변경 성공
#  => 모든 기기 로그아웃 + 옛 비밀번호 로그인 불가 + 새 비밀번호 로그인 가능
#  => 다른 사용자는 영향 없음
async def test_change_password_success(client, make_user, auth_header, session_factory):
    # 1. 준비: 내가 2개 기기(PC, 휴대폰)에서 로그인 + 다른 사용자도 로그인
    me = await make_user("me@corp.com")
    other = await make_user("other@corp.com")
    await sign_in(client, "me@corp.com")
    phone_refresh = (await sign_in(client, "me@corp.com")).json()["data"]["refresh_token"]
    await sign_in(client, "other@corp.com")

    # 2. 실행
    response = await client.patch("/auth/password", json=password_body(), headers=auth_header(me))

    # 3. 검증
    assert response.status_code == 200
    assert response.json()["data"]["signed_out_sessions"] == 2
    assert await count_refresh_tokens(session_factory, me.id) == 0  # 내 기기는 모두 로그아웃
    assert await count_refresh_tokens(session_factory, other.id) == 1  # 다른 사용자는 그대로
    re_token = await client.post("/auth/re-token", json={"refresh_token": phone_refresh})
    assert re_token.status_code == 401  # 휴대폰에 남은 토큰으로도 재발급 불가
    assert (await sign_in(client, "me@corp.com")).status_code == 401  # 옛 비밀번호
    new_password_sign_in = await sign_in(client, "me@corp.com", "newpass123")
    assert new_password_sign_in.status_code == 200  # 새 비밀번호


# 로그인하지 않으면 401
async def test_change_password_without_token(client):
    response = await client.patch("/auth/password", json=password_body())
    assert response.status_code == 401


# 잘못된 요청은 모두 400이고, 실패했을 때는 로그아웃(토큰 삭제)도 일어나면 안 됨
async def test_change_password_invalid_requests(client, make_user, auth_header, session_factory):
    me = await make_user("me@corp.com")
    await sign_in(client, "me@corp.com")
    headers = auth_header(me)

    # 새 비밀번호 확인값이 다름
    mismatch = await client.patch(
        "/auth/password", json=password_body(confirm="different123"), headers=headers
    )
    # 현재 비밀번호가 틀림
    wrong_current = await client.patch(
        "/auth/password", json=password_body(current="wrongpass1"), headers=headers
    )
    # 새 비밀번호가 현재 비밀번호와 같음
    same = await client.patch(
        "/auth/password", json=password_body(new=TEST_PASSWORD), headers=headers
    )

    assert mismatch.status_code == 400
    assert wrong_current.status_code == 400
    assert same.status_code == 400
    assert await count_refresh_tokens(session_factory, me.id) == 1  # 토큰은 그대로


# 관리자도 자기 비밀번호는 같은 방식으로 변경 (권한과 상관없이 로그인한 사용자 누구나)
async def test_change_password_admin(client, make_user, auth_header):
    admin = await make_user("admin@corp.com", role=UserRole.ADMIN)
    response = await client.patch(
        "/auth/password", json=password_body(), headers=auth_header(admin)
    )
    assert response.status_code == 200
