#  * 새 파일 추가 - 사용자(user) API 테스트
#  - 변경: 관리자 계정 생성 / 내 정보 조회 / 목록 조회 / 활성화 / 권한 변경의 동작을 코드로 저장
#
# 📌 이 파일에서 새로 등장하는 pytest 기능
#  1) 파일 안에서만 쓰는 fixture (admin, manager, normal_user)
#     - fixture가 다른 fixture(make_user)를 매개변수로 받아서 사용할 수도 있음
#  2) @pytest.mark.parametrize: 같은 테스트를 "값만 바꿔서" 여러 번 실행
#     - 예) 잘못된 입력값 4종류를 테스트 함수 하나로 검사 => 결과에는 테스트 4개로 표시됨

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from src.core.config import get_settings
from src.services.iam.user.enums import UserRole
from tests.constants import TEST_PASSWORD


# ─────────────────────────────────────────────
# 이 파일에서 공통으로 쓰는 fixture (권한별 사용자)
# ─────────────────────────────────────────────
@pytest.fixture
async def admin(make_user):
    return await make_user("admin@corp.com", role=UserRole.ADMIN)


@pytest.fixture
async def manager(make_user):
    return await make_user("manager@corp.com", role=UserRole.MANAGER)


@pytest.fixture
async def normal_user(make_user):
    return await make_user("user@corp.com", role=UserRole.USER)


# ─────────────────────────────────────────────
# 1. 관리자 계정 생성 (POST /users/) - admin 전용
# ─────────────────────────────────────────────
# 관리자 계정 생성 요청 본문
def create_body(email="new@corp.com", role="manager"):
    return {
        "email": email,
        "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD,
        "role": role,
    }


# admin이 만들면 => 지정한 권한 + 즉시 사용 가능(is_active=True)
async def test_create_user_by_admin(client, admin, auth_header):
    response = await client.post("/users/", json=create_body(), headers=auth_header(admin))

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["role"] == "manager"
    assert data["is_active"] is True


# admin이 아니면 사용할 수 없음 (토큰 없음 401 / manager, user 403)
async def test_create_user_permission(client, manager, normal_user, auth_header):
    no_token = await client.post("/users/", json=create_body())
    by_manager = await client.post("/users/", json=create_body(), headers=auth_header(manager))
    by_user = await client.post("/users/", json=create_body(), headers=auth_header(normal_user))

    assert no_token.status_code == 401
    assert by_manager.status_code == 403
    assert by_user.status_code == 403


# ─────────────────────────────────────────────
# 2. 내 정보 조회 (GET /users/me) - 로그인한 사용자 누구나
# ─────────────────────────────────────────────
# 로그인한 사용자 => 자기 정보 조회 성공, 비밀번호 해시는 응답에 없어야 함
async def test_get_me_success(client, normal_user, auth_header):
    response = await client.get("/users/me", headers=auth_header(normal_user))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == "user@corp.com"
    assert "hashed_password" not in data


# 토큰이 없으면 401 + WWW-Authenticate 헤더(Bearer 토큰이 필요하다는 HTTP 표준 안내)
async def test_get_me_without_token(client):
    response = await client.get("/users/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


# 만료된 액세스 토큰이면 401
async def test_get_me_with_expired_token(client, normal_user):
    # 만료 시각이 1분 전인 토큰을 직접 만듦
    settings = get_settings()
    payload = {
        "sub": str(normal_user.id),
        "type": "access",
        "exp": datetime.now(UTC) - timedelta(minutes=1),
    }
    expired_token = jwt.encode(payload, settings.access_token_secret, algorithm="HS256")

    response = await client.get("/users/me", headers={"Authorization": f"Bearer {expired_token}"})

    assert response.status_code == 401


# 비활성화된 계정의 토큰이면 401 (토큰 자체는 유효해도 DB의 is_active를 매번 확인)
async def test_get_me_inactive_user(client, make_user, auth_header):
    inactive = await make_user("wait@corp.com", is_active=False)
    response = await client.get("/users/me", headers=auth_header(inactive))
    assert response.status_code == 401


# ─────────────────────────────────────────────
# 3. 사용자 목록 조회 (GET /users/) - admin, manager 전용
# ─────────────────────────────────────────────
# 목록 조회 테스트용 사용자 25명 만들기
#  - 1번 사용자가 가장 먼저 가입, 25번 사용자가 가장 최근 가입
#  - 3의 배수 번호(3, 6, 9 ... 24 => 8명)는 승인 대기(is_active=False)
@pytest.fixture
async def many_users(make_user):
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    users = []
    for number in range(1, 26):
        user = await make_user(
            f"user{number:02d}@corp.com",  # user01@corp.com ~ user25@corp.com
            is_active=(number % 3 != 0),
            created_at=base_time + timedelta(days=number),
        )
        users.append(user)
    return users


# 목록 조회 API 호출 도우미 (params: 주소 뒤 ?a=1&b=2 에 들어갈 값)
async def get_users(client, headers, **params):
    return await client.get("/users/", params=params, headers=headers)


# 권한: 토큰 없음 401 / user 403 / manager, admin 200
async def test_list_users_permission(client, admin, manager, normal_user, auth_header):
    assert (await client.get("/users/")).status_code == 401
    assert (await get_users(client, auth_header(normal_user))).status_code == 403
    assert (await get_users(client, auth_header(manager))).status_code == 200
    assert (await get_users(client, auth_header(admin))).status_code == 200


# 기본값 => 최신 가입순, 한 페이지 20명, 페이지 정보 포함
async def test_list_users_default(client, admin, auth_header, many_users):
    # admin(1명) + many_users(25명) = 전체 26명
    response = await get_users(client, auth_header(admin))

    data = response.json()["data"]
    assert data["total"] == 26
    assert data["page"] == 1
    assert data["size"] == 20
    assert data["total_pages"] == 2  # 26명 / 20명 = 2페이지
    assert len(data["items"]) == 20
    # 가장 최근에 만든 admin이 맨 앞, 그 다음은 user25, user24 ... 순서
    emails = [item["email"] for item in data["items"]]
    assert emails[:3] == ["admin@corp.com", "user25@corp.com", "user24@corp.com"]


# 2페이지 => 남은 6명
async def test_list_users_second_page(client, admin, auth_header, many_users):
    response = await get_users(client, auth_header(admin), page=2)

    data = response.json()["data"]
    assert data["page"] == 2
    assert len(data["items"]) == 6
    assert data["items"][-1]["email"] == "user01@corp.com"  # 가장 먼저 가입한 사용자가 마지막


# 승인 대기(is_active=false) 필터 => 3의 배수 번호 8명만
async def test_list_users_filter_inactive(client, admin, auth_header, many_users):
    response = await get_users(client, auth_header(admin), is_active="false", size=100)

    data = response.json()["data"]
    assert data["total"] == 8
    assert all(item["is_active"] is False for item in data["items"])


# 권한(role) 필터
async def test_list_users_filter_role(client, admin, manager, auth_header, many_users):
    response = await get_users(client, auth_header(admin), role="manager")

    data = response.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["email"] == "manager@corp.com"


# email 부분 검색 (대소문자 구분 없음)
async def test_list_users_search_email(client, admin, auth_header, many_users):
    response = await get_users(client, auth_header(admin), email="USER1")

    # user10 ~ user19 => 10명
    assert response.json()["data"]["total"] == 10


# email 검색어의 % 는 "모든 글자"가 아니라 "진짜 % 글자"로 검색되어야 함
async def test_list_users_search_email_escape(client, admin, make_user, auth_header):
    await make_user("sale_50%@corp.com")

    percent = await get_users(client, auth_header(admin), email="%")
    underscore = await get_users(client, auth_header(admin), email="e_5")

    assert percent.json()["data"]["total"] == 1
    assert underscore.json()["data"]["total"] == 1


# 오래된 순(order=asc) 정렬
async def test_list_users_sort_oldest_first(client, admin, auth_header, many_users):
    response = await get_users(client, auth_header(admin), order="asc", size=3)

    emails = [item["email"] for item in response.json()["data"]["items"]]
    assert emails == ["user01@corp.com", "user02@corp.com", "user03@corp.com"]


# 필터 + 정렬 조합 => 승인 대기 계정을 오래 기다린 순으로
async def test_list_users_filter_and_sort(client, admin, auth_header, many_users):
    response = await get_users(client, auth_header(admin), is_active="false", order="asc", size=3)

    emails = [item["email"] for item in response.json()["data"]["items"]]
    assert emails == ["user03@corp.com", "user06@corp.com", "user09@corp.com"]


# 잘못된 쿼리 값은 모두 422
#  - @pytest.mark.parametrize("이름", [값1, 값2 ...]): 값마다 테스트를 한 번씩 실행
#  - 아래 4개 값이 각각 params로 들어가서 => 테스트 4개로 실행됨
@pytest.mark.parametrize(
    "params",
    [
        {"sort_by": "hashed_password"},  # 허용하지 않은 정렬 기준 (민감한 컬럼)
        {"page": 0},  # 페이지는 1부터
        {"size": 101},  # 한 페이지 최대 100명
        {"role": "owner"},  # 없는 권한
    ],
)
async def test_list_users_invalid_params(client, admin, auth_header, params):
    response = await get_users(client, auth_header(admin), **params)
    assert response.status_code == 422


# ─────────────────────────────────────────────
# 4. 사용자 활성화 (PATCH /users/{user_id}/active) - admin, manager 전용
# ─────────────────────────────────────────────
# 활성화 API 호출 도우미
async def set_active(client, headers, user_id, is_active):
    return await client.patch(
        f"/users/{user_id}/active", json={"is_active": is_active}, headers=headers
    )


# manager가 승인 대기 중인 user를 승인 => 성공
async def test_activate_user_by_manager(client, manager, make_user, auth_header):
    waiting = await make_user("wait@corp.com", is_active=False)

    response = await set_active(client, auth_header(manager), waiting.id, True)

    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is True
    # 승인된 사용자는 이제 로그인 가능
    sign_in = await client.post(
        "/auth/sign-in", json={"email": "wait@corp.com", "password": TEST_PASSWORD}
    )
    assert sign_in.status_code == 200


# manager는 admin, 다른 manager를 변경할 수 없음 (403)
async def test_manager_cannot_change_admin_or_manager(
    client, admin, manager, make_user, auth_header
):
    other_manager = await make_user("manager2@corp.com", role=UserRole.MANAGER)
    headers = auth_header(manager)

    to_admin = await set_active(client, headers, admin.id, False)
    to_manager = await set_active(client, headers, other_manager.id, False)

    assert to_admin.status_code == 403
    assert to_manager.status_code == 403


# admin이 계정을 비활성화하면 => 그 사용자의 토큰은 즉시 사용 불가 (401)
async def test_deactivate_user_takes_effect_immediately(client, admin, manager, auth_header):
    manager_headers = auth_header(manager)
    assert (await client.get("/users/me", headers=manager_headers)).status_code == 200

    response = await set_active(client, auth_header(admin), manager.id, False)

    assert response.status_code == 200
    assert (await client.get("/users/me", headers=manager_headers)).status_code == 401


# user는 사용할 수 없음 (403)
async def test_activate_user_by_normal_user(client, normal_user, make_user, auth_header):
    waiting = await make_user("wait@corp.com", is_active=False)
    response = await set_active(client, auth_header(normal_user), waiting.id, True)
    assert response.status_code == 403


# 자기 자신 변경 403 / 없는 사용자 404
async def test_activate_self_or_unknown_user(client, admin, auth_header):
    headers = auth_header(admin)

    self_change = await set_active(client, headers, admin.id, False)
    unknown = await set_active(client, headers, 99999, True)

    assert self_change.status_code == 403
    assert unknown.status_code == 404


# ─────────────────────────────────────────────
# 5. 권한 변경 (PATCH /users/{user_id}/role) - admin 전용
# ─────────────────────────────────────────────
# 권한 변경 API 호출 도우미
async def set_role(client, headers, user_id, role):
    return await client.patch(f"/users/{user_id}/role", json={"role": role}, headers=headers)


# admin이 user를 manager로 변경 => 다시 로그인하지 않아도 즉시 manager 기능 사용 가능
async def test_change_role_takes_effect_immediately(client, admin, normal_user, auth_header):
    user_headers = auth_header(normal_user)
    assert (await get_users(client, user_headers)).status_code == 403  # 변경 전: 목록 조회 불가

    response = await set_role(client, auth_header(admin), normal_user.id, "manager")

    assert response.status_code == 200
    assert response.json()["data"]["role"] == "manager"
    assert (await get_users(client, user_headers)).status_code == 200  # 변경 후: 즉시 가능


# admin이 아니면 사용할 수 없음 (manager 403)
async def test_change_role_by_manager(client, manager, normal_user, auth_header):
    response = await set_role(client, auth_header(manager), normal_user.id, "admin")
    assert response.status_code == 403


# 자기 자신 변경 403 / 없는 권한 값 422
async def test_change_role_self_or_invalid(client, admin, normal_user, auth_header):
    headers = auth_header(admin)

    self_change = await set_role(client, headers, admin.id, "user")
    invalid_role = await set_role(client, headers, normal_user.id, "owner")

    assert self_change.status_code == 403
    assert invalid_role.status_code == 422
