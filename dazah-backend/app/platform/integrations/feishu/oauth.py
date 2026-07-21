"""Feishu OAuth client for SSO login.

Uses raw httpx because the OAuth endpoints are not fully covered by the
lark-oapi SDK.  The flow follows the official Feishu documentation:

  Step 1 – Authorize:  GET  https://accounts.feishu.cn/open-apis/authen/v1/authorize
  Step 2 – Token:      POST https://open.feishu.cn/open-apis/authen/v2/oauth/token
  Step 3 – User Info:  GET  https://open.feishu.cn/open-apis/authen/v1/user_info
  Step 4 – Refresh:    POST https://open.feishu.cn/open-apis/authen/v2/oauth/token

Ref: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/authen-v1/login-overview
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


def _normalize_oauth_token_response(data: dict) -> dict:
    """Return the token payload regardless of Feishu response envelope shape."""
    if data.get("code", 0) != 0:
        raise OAuthError(
            f"OAuth token request failed: code={data.get('code')}, "
            f"error={data.get('error')}, "
            f"desc={data.get('error_description') or data.get('msg', '')}",
        )
    payload = data.get("data")
    if isinstance(payload, dict):
        return payload
    return data


class FeishuOAuthClient:
    """Handles the OAuth 2.0 authorization-code flow against Feishu."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        redirect_uri: str,
        scopes: str,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes

    @classmethod
    def from_settings(cls) -> FeishuOAuthClient:
        s = get_settings()
        return cls(
            app_id=s.FEISHU_APP_ID,
            app_secret=s.FEISHU_APP_SECRET,
            redirect_uri=s.FEISHU_REDIRECT_URI,
            scopes=s.FEISHU_SCOPES,
        )

    # ── URL builders ────────────────────────────────────────────────

    def build_authorize_url(self, state: str) -> str:
        """Return the full Feishu authorization URL to redirect the user to."""
        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": self.scopes,
        }
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    # ── Token operations ────────────────────────────────────────────

    async def exchange_code(self, code: str) -> dict:
        """Exchange an authorization code for tokens.

        Returns dict with keys: access_token, token_type, expires_in,
        refresh_token, refresh_token_expires_in, scope.
        """
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _TOKEN_URL,
                json=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

        return _normalize_oauth_token_response(data)

    async def refresh_access_token(self, refresh_token: str) -> dict:
        """Refresh a user_access_token using a refresh_token."""
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _TOKEN_URL,
                json=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

        return _normalize_oauth_token_response(data)

    # ── User info ───────────────────────────────────────────────────

    async def get_user_info(self, user_access_token: str) -> dict:
        """Fetch the authenticated user's profile from Feishu.

        Returns dict with keys: name, en_name, avatar_url, avatar_thumb,
        avatar_middle, avatar_big, open_id, union_id, email,
        enterprise_email, user_id, mobile, tenant_key.
        """
        headers = {"Authorization": f"Bearer {user_access_token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _USER_INFO_URL, headers=headers, timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != 0:
            raise OAuthError(
                f"get_user_info failed: code={data.get('code')}, "
                f"msg={data.get('msg')}",
            )
        return data.get("data", {})


class OAuthError(Exception):
    """Raised when an OAuth operation fails."""
