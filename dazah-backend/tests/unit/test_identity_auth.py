from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.main import app
from app.platform.identity import deps
from app.platform.identity.models import FeishuUserToken
from app.platform.identity.service import generate_state_token


def make_request(authorization: str | None = None) -> Request:
    headers = []
    if authorization:
        headers.append((b"authorization", authorization.encode("utf-8")))
    return Request({"type": "http", "headers": headers})


def make_settings() -> SimpleNamespace:
    return SimpleNamespace(
        SECRET_KEY="test-secret",
        FEISHU_APP_ID="cli_test",
        FEISHU_APP_SECRET="secret",
        FEISHU_REDIRECT_URI="http://localhost:3000/api/v1/identity/auth/callback",
        FEISHU_SCOPES="contact:user.base:readonly",
        FRONTEND_URL="http://localhost:3000",
        JWT_EXPIRE_SECONDS=86400,
        is_production=False,
        effective_local_login_mode="enabled",
    )


async def fake_get_db():
    yield object()


def test_local_login_mode_defaults_are_environment_safe() -> None:
    development = Settings.model_construct(
        APP_ENV="development",
        LOCAL_LOGIN_MODE=None,
    )
    production = Settings.model_construct(
        APP_ENV="production",
        LOCAL_LOGIN_MODE=None,
    )

    assert development.effective_local_login_mode == "enabled"
    assert production.effective_local_login_mode == "disabled"


def test_production_requires_an_accessible_administrator_path() -> None:
    settings = Settings.model_construct(
        APP_ENV="production",
        LOCAL_LOGIN_MODE=None,
        SECRET_KEY="secret",
        ENCRYPTION_KEY="encryption-key",
        FRONTEND_URL="https://factory.example.com",
        SSO_ADMIN_IDENTIFIERS="",
        BOOTSTRAP_ADMIN_USERNAME="",
        BOOTSTRAP_ADMIN_PASSWORD="",
    )

    with pytest.raises(RuntimeError, match="SSO_ADMIN_IDENTIFIERS"):
        settings.check()


def test_production_accepts_a_configured_sso_administrator() -> None:
    settings = Settings.model_construct(
        APP_ENV="production",
        LOCAL_LOGIN_MODE=None,
        SECRET_KEY="secret",
        ENCRYPTION_KEY="encryption-key",
        FRONTEND_URL="https://factory.example.com",
        SSO_ADMIN_IDENTIFIERS="admin@example.com",
        BOOTSTRAP_ADMIN_USERNAME="",
        BOOTSTRAP_ADMIN_PASSWORD="",
    )

    settings.check()


def test_module_access_mode_defaults_to_all() -> None:
    development = Settings.model_construct(
        APP_ENV="development",
        MODULE_ACCESS_MODE=None,
    )
    production = Settings.model_construct(
        APP_ENV="production",
        MODULE_ACCESS_MODE=None,
    )
    test = Settings.model_construct(
        APP_ENV="test",
        MODULE_ACCESS_MODE=None,
    )

    assert development.effective_module_access_mode == "all"
    assert production.effective_module_access_mode == "all"
    assert test.effective_module_access_mode == "all"


def test_module_access_mode_accepts_explicit_override() -> None:
    development = Settings.model_construct(
        APP_ENV="development",
        MODULE_ACCESS_MODE="roles",
    )
    production = Settings.model_construct(
        APP_ENV="production",
        MODULE_ACCESS_MODE="all",
    )

    assert development.effective_module_access_mode == "roles"
    assert production.effective_module_access_mode == "all"


@pytest.mark.anyio
async def test_current_user_is_none_without_token() -> None:
    user = await deps.get_current_user(
        make_request(),
        db=object(),
        settings=make_settings(),
        auth_token=None,
    )

    assert user is None


@pytest.mark.anyio
async def test_current_user_is_none_for_invalid_token() -> None:
    user = await deps.get_current_user(
        make_request("Bearer not-a-valid-jwt"),
        db=object(),
        settings=make_settings(),
        auth_token=None,
    )

    assert user is None


@pytest.mark.anyio
async def test_me_endpoint_requires_login() -> None:
    app.dependency_overrides[get_db] = fake_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/identity/me")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 401
    assert response.json()["message"] == "Login required"


@pytest.mark.anyio
async def test_feishu_login_redirects_and_sets_state_cookie() -> None:
    app.dependency_overrides[get_settings] = make_settings
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/identity/auth/login?next=/quality",
                follow_redirects=False,
            )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 302
    assert response.headers["location"].startswith(
        "https://accounts.feishu.cn/open-apis/authen/v1/authorize?"
    )
    assert "client_id=cli_test" in response.headers["location"]
    assert "feishu_oauth_state=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


@pytest.mark.anyio
async def test_feishu_callback_rejects_invalid_state() -> None:
    app.dependency_overrides[get_settings] = make_settings
    app.dependency_overrides[get_db] = fake_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/identity/auth/callback?code=abc&state=bad",
                cookies={"feishu_oauth_state": "other"},
                follow_redirects=False,
            )
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:3000/login?error=invalid_state"


@pytest.mark.anyio
async def test_feishu_callback_rejects_missing_state_cookie() -> None:
    state = generate_state_token("/quality")
    app.dependency_overrides[get_settings] = make_settings
    app.dependency_overrides[get_db] = fake_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/identity/auth/callback?code=abc&state={state}",
                follow_redirects=False,
            )
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:3000/login?error=invalid_state"


@pytest.mark.anyio
async def test_feishu_callback_success_redirects_token(monkeypatch) -> None:
    async def fake_handle_oauth_callback(db, code):
        user = SimpleNamespace(id=uuid4(), name="飞书用户")
        return user, "jwt-token"

    from app.platform.identity import service

    monkeypatch.setattr(service, "handle_oauth_callback", fake_handle_oauth_callback)

    state = generate_state_token("/warehouse")
    app.dependency_overrides[get_settings] = make_settings
    app.dependency_overrides[get_db] = fake_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/identity/auth/callback?code=abc&state={state}",
                cookies={"feishu_oauth_state": state},
                follow_redirects=False,
            )
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:3000/warehouse"
    assert "auth_token=jwt-token" in response.headers["set-cookie"]
    assert "token=" not in response.headers["location"]


@pytest.mark.anyio
async def test_local_login_still_returns_token(monkeypatch) -> None:
    async def fake_authenticate_local_user(db, *, username, password):
        user = SimpleNamespace(
            id=uuid4(),
            name="本地管理员",
            username=username,
            role="admin",
            status="active",
            auth_source="local",
            en_name=None,
            email=None,
            enterprise_email=None,
            mobile=None,
            avatar_url=None,
            avatar_thumb=None,
            avatar_middle=None,
            avatar_big=None,
            employee_no=None,
            department=None,
            position=None,
            feishu_user_id=None,
            feishu_open_id=None,
            feishu_union_id=None,
            tenant_key=None,
        )
        return user, "local-token"

    from app.platform.identity import service

    monkeypatch.setattr(
        service,
        "authenticate_local_user",
        fake_authenticate_local_user,
    )

    app.dependency_overrides[get_db] = fake_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/identity/auth/local/login",
                json={"username": "admin", "password": "secret"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert "auth_token=local-token" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    payload = response.json()
    assert payload["data"]["access_token"] == "local-token"
    assert payload["data"]["user"]["username"] == "admin"


@pytest.mark.anyio
async def test_local_login_is_rejected_when_disabled(monkeypatch) -> None:
    async def unexpected_authenticate(*args, **kwargs):
        pytest.fail("disabled local login must not verify credentials")

    from app.platform.identity import service

    monkeypatch.setattr(
        service,
        "authenticate_local_user",
        unexpected_authenticate,
    )

    settings = make_settings()
    settings.effective_local_login_mode = "disabled"
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = fake_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/identity/auth/local/login",
                json={"username": "admin", "password": "secret"},
            )
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 403
    assert "本地账号登录已禁用" in response.text


@pytest.mark.anyio
async def test_admin_only_local_login_rejects_regular_user(monkeypatch) -> None:
    async def fake_authenticate_local_user(db, *, username, password):
        return SimpleNamespace(role="user"), "local-token"

    from app.platform.identity import service

    monkeypatch.setattr(
        service,
        "authenticate_local_user",
        fake_authenticate_local_user,
    )

    settings = make_settings()
    settings.effective_local_login_mode = "admin_only"
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = fake_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/identity/auth/local/login",
                json={"username": "user", "password": "secret"},
            )
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 403
    assert "应急登录仅允许管理员账号" in response.text


@pytest.mark.anyio
async def test_oauth_callback_saves_encrypted_feishu_user_tokens(monkeypatch) -> None:
    user_id = uuid4()

    class FakeDb:
        def __init__(self) -> None:
            self.commits = 0
            self.flushes = 0

        async def flush(self) -> None:
            self.flushes += 1

        async def commit(self) -> None:
            self.commits += 1

    class FakeUserRepo:
        def __init__(self) -> None:
            self.created_kwargs: dict | None = None

        async def get_by_feishu_open_id(self, db, open_id):
            return None

        async def get_by_feishu_user_id(self, db, user_id):
            return None

        async def create(self, db, **kwargs):
            self.created_kwargs = kwargs
            return SimpleNamespace(
                id=user_id,
                name=kwargs["name"],
                role=kwargs["role"],
                status=kwargs["status"],
                auth_source=kwargs["auth_source"],
                feishu_open_id=kwargs["feishu_open_id"],
                feishu_user_id=kwargs["feishu_user_id"],
                feishu_union_id=kwargs["feishu_union_id"],
                tenant_key=kwargs["tenant_key"],
            )

    class FakeTokenRepo:
        def __init__(self) -> None:
            self.saved: FeishuUserToken | None = None

        async def get_by_user_and_app(self, db, *, local_user_id, app_id):
            return None

        async def save(self, db, token):
            self.saved = token
            return token

    class FakeOAuth:
        app_id = "cli_test"

        async def exchange_code(self, code):
            return {
                "access_token": "user-token",
                "refresh_token": "refresh-token",
                "expires_in": 7200,
                "refresh_token_expires_in": 86400,
                "scope": "contact:user.base:readonly",
                "token_type": "Bearer",
            }

        async def get_user_info(self, user_access_token):
            return {
                "name": "飞书用户",
                "open_id": "ou_test",
                "user_id": "u_test",
                "union_id": "on_test",
                "tenant_key": "tenant_test",
            }

    fake_user_repo = FakeUserRepo()
    fake_token_repo = FakeTokenRepo()
    from app.platform.identity import service

    monkeypatch.setattr(service, "_repo", fake_user_repo)
    monkeypatch.setattr(service, "_feishu_user_token_repo", fake_token_repo)
    monkeypatch.setattr(service.FeishuOAuthClient, "from_settings", lambda: FakeOAuth())

    async def fake_directory_profile(*args, **kwargs):
        return {
            "name": "飞书用户",
            "employee_no": "E001",
            "department_ids": ["od_quality"],
            "department_path": [
                {
                    "department_id": "od_quality",
                    "department_name": "质量管理部",
                }
            ],
            "job_title": "质量工程师",
        }

    monkeypatch.setattr(
        service,
        "_get_oauth_directory_profile",
        fake_directory_profile,
    )
    monkeypatch.setattr(service, "encrypt_secret", lambda value: f"enc:{value}")
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(
            SECRET_KEY="test-secret",
            JWT_EXPIRE_SECONDS=86400,
            SSO_ADMIN_IDENTIFIERS="",
        ),
    )

    db = FakeDb()
    user, jwt_token = await service.handle_oauth_callback(db, "auth-code")

    assert user.id == user_id
    assert jwt_token
    assert db.commits == 1
    assert user.role == "user"
    assert fake_user_repo.created_kwargs is not None
    assert fake_user_repo.created_kwargs["department"] == "质量管理部"
    assert fake_user_repo.created_kwargs["position"] == "质量工程师"
    assert fake_user_repo.created_kwargs["employee_no"] == "E001"
    assert fake_user_repo.created_kwargs["feishu_department_ids"] == '["od_quality"]'
    assert fake_token_repo.saved is not None
    assert fake_token_repo.saved.local_user_id == user_id
    assert fake_token_repo.saved.app_id == "cli_test"
    assert fake_token_repo.saved.encrypted_user_access_token == "enc:user-token"
    assert fake_token_repo.saved.encrypted_refresh_token == "enc:refresh-token"
    assert fake_token_repo.saved.access_token_expires_at is not None
    assert fake_token_repo.saved.refresh_token_expires_at is not None


@pytest.mark.anyio
async def test_get_valid_feishu_user_access_token_refreshes_and_replaces_tokens(
    monkeypatch,
) -> None:
    user_id = uuid4()
    now = datetime.now(UTC)
    stored = FeishuUserToken(
        local_user_id=user_id,
        app_id="cli_test",
        encrypted_user_access_token="enc:old-token",
        encrypted_refresh_token="enc:old-refresh",
        access_token_expires_at=now - timedelta(minutes=1),
        status="active",
    )

    class FakeDb:
        def __init__(self) -> None:
            self.flushes = 0

        async def flush(self) -> None:
            self.flushes += 1

    class FakeUserRepo:
        async def get_by_id(self, db, user_id):
            return SimpleNamespace(
                id=user_id,
                name="飞书用户",
                status="active",
                feishu_open_id="ou_test",
                feishu_user_id="u_test",
                feishu_union_id="on_test",
                tenant_key="tenant_test",
            )

    class FakeTokenRepo:
        async def get_by_user_and_app(self, db, *, local_user_id, app_id):
            return stored

    class FakeOAuth:
        async def refresh_access_token(self, refresh_token):
            assert refresh_token == "old-refresh"
            return {
                "access_token": "new-token",
                "refresh_token": "new-refresh",
                "expires_in": 7200,
                "refresh_token_expires_in": 86400,
            }

    from app.platform.identity import service

    monkeypatch.setattr(service, "_repo", FakeUserRepo())
    monkeypatch.setattr(service, "_feishu_user_token_repo", FakeTokenRepo())
    monkeypatch.setattr(service.FeishuOAuthClient, "from_settings", lambda: FakeOAuth())
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(FEISHU_APP_ID="cli_test"),
    )
    monkeypatch.setattr(
        service,
        "decrypt_secret",
        lambda value: value.removeprefix("enc:"),
    )
    monkeypatch.setattr(service, "encrypt_secret", lambda value: f"enc:{value}")

    token = await service.get_valid_feishu_user_access_token(FakeDb(), user_id=user_id)

    assert token == "new-token"
    assert stored.encrypted_user_access_token == "enc:new-token"
    assert stored.encrypted_refresh_token == "enc:new-refresh"
    assert stored.status == "active"
    assert stored.last_error is None
    assert stored.last_refreshed_at is not None
