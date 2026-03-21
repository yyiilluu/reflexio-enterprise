"""
OAuth authentication endpoints for Google and GitHub.

Provides registration and login flows via OAuth providers. Uses signed JWT state
tokens to carry action context (register vs login, invitation code) through the
OAuth redirect dance.
"""

import json
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from reflexio.server.site_var.feature_flags import (
    get_all_feature_flags,
    is_invitation_only_enabled,
)
from sqlalchemy.orm import Session

from reflexio_ext.server.api_endpoints.login import (
    ALGORITHM,
    SECRET_KEY,
    generate_short_api_key,
    register_organization,
)
from reflexio_ext.server.db.db_operations import (
    claim_invitation_code,
    create_api_token,
    get_api_tokens_by_org_id,
    get_db_session,
    get_organization_by_email,
    release_invitation_code,
    update_organization,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["oauth"])

# OAuth state token expiry
OAUTH_STATE_EXPIRE_MINUTES = 10

# Provider configurations
OAUTH_PROVIDERS = {
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scopes": "openid email profile",
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scopes": "user:email",
    },
}


def _get_client_id(provider: str) -> str | None:
    return os.getenv(f"{provider.upper()}_CLIENT_ID")


def _get_client_secret(provider: str) -> str | None:
    return os.getenv(f"{provider.upper()}_CLIENT_SECRET")


def get_configured_oauth_providers() -> list[str]:
    """
    Return list of OAuth providers that have both client_id and client_secret configured.

    Returns:
        list[str]: List of provider names (e.g. ["google", "github"])
    """
    return [p for p in OAUTH_PROVIDERS if _get_client_id(p) and _get_client_secret(p)]


def _get_frontend_url(request: Request) -> str:
    """
    Determine the frontend URL for redirects.

    Uses FRONTEND_URL env var if set, otherwise derives from the request origin.

    Args:
        request: The incoming FastAPI request

    Returns:
        str: Frontend base URL (no trailing slash)
    """
    frontend_url = os.getenv("FRONTEND_URL")
    if frontend_url:
        return frontend_url.rstrip("/")

    # Derive from request: the request comes through Next.js rewrite,
    # so use the Origin or Referer header
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")

    referer = request.headers.get("referer")
    if referer:
        from urllib.parse import urlparse

        parsed = urlparse(referer)
        return f"{parsed.scheme}://{parsed.netloc}"

    # Fallback: use FRONTEND_PORT env var or default 8080
    frontend_port = os.getenv("FRONTEND_PORT", "8080")
    return f"http://localhost:{frontend_port}"


def _get_callback_url(request: Request, provider: str) -> str:
    """
    Build the OAuth callback URL.

    The callback goes through the Next.js /api/* rewrite to reach the backend.

    Args:
        request: The incoming request
        provider: OAuth provider name

    Returns:
        str: Full callback URL
    """
    frontend_url = _get_frontend_url(request)
    return f"{frontend_url}/api/auth/{provider}/callback"


def _create_oauth_state(
    action: str,
    provider: str,
    invitation_code: str | None = None,
) -> str:
    """
    Create a signed JWT state token for OAuth flow.

    Args:
        action: "login" or "register"
        provider: OAuth provider name
        invitation_code: Optional invitation code (for registration)

    Returns:
        str: Signed JWT state token
    """
    expire = datetime.now(UTC) + timedelta(minutes=OAUTH_STATE_EXPIRE_MINUTES)
    payload = {
        "action": action,
        "provider": provider,
        "nonce": secrets.token_urlsafe(16),
        "exp": expire,
    }
    if invitation_code:
        payload["invitation_code"] = invitation_code
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _verify_oauth_state(state: str) -> dict | None:
    """
    Verify and decode an OAuth state JWT.

    Args:
        state: The JWT state token

    Returns:
        dict with action, provider, invitation_code (if present), or None if invalid
    """
    try:
        return jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


async def _exchange_code_for_token(
    provider: str, code: str, redirect_uri: str
) -> str | None:
    """
    Exchange an authorization code for an access token.

    Args:
        provider: OAuth provider name
        code: Authorization code from provider
        redirect_uri: The callback URL used in the authorization request

    Returns:
        str: Access token, or None on failure
    """
    config = OAUTH_PROVIDERS[provider]
    client_id = _get_client_id(provider)
    client_secret = _get_client_secret(provider)

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }

    headers = {}
    if provider == "google":
        data["grant_type"] = "authorization_code"
    elif provider == "github":
        headers["Accept"] = "application/json"

    async with httpx.AsyncClient() as client:
        resp = await client.post(config["token_url"], data=data, headers=headers)
        if resp.status_code != 200:
            logger.error("OAuth token exchange failed for %s: %s", provider, resp.text)
            return None

        token_data = resp.json()
        return token_data.get("access_token")


async def _get_user_email(provider: str, access_token: str) -> str | None:
    """
    Get the user's primary email from the OAuth provider.

    Args:
        provider: OAuth provider name
        access_token: Provider access token

    Returns:
        str: User's email address, or None on failure
    """
    config = OAUTH_PROVIDERS[provider]
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(config["userinfo_url"], headers=headers)
        if resp.status_code != 200:
            logger.error("Failed to get user info from %s: %s", provider, resp.text)
            return None

        user_data = resp.json()

        if provider == "google":
            return user_data.get("email")
        if provider == "github":
            email = user_data.get("email")
            if email:
                return email
            # GitHub may not return email in profile; fetch from /user/emails
            emails_resp = await client.get(
                "https://api.github.com/user/emails", headers=headers
            )
            if emails_resp.status_code == 200:
                for e in emails_resp.json():
                    if e.get("primary") and e.get("verified"):
                        return e.get("email")
            return None

    return None


def _redirect_frontend_error(frontend_url: str, error: str) -> RedirectResponse:
    """Build a redirect to the frontend callback page with an error."""
    params = urlencode({"error": error})
    return RedirectResponse(url=f"{frontend_url}/auth/callback?{params}")


def _redirect_frontend_success(
    frontend_url: str,
    token: str,
    email: str,
    feature_flags: dict | None = None,
) -> RedirectResponse:
    """Build a redirect to the frontend callback page with success data."""
    params = {
        "token": token,
        "email": email,
    }
    if feature_flags:
        params["feature_flags"] = json.dumps(feature_flags)
    return RedirectResponse(url=f"{frontend_url}/auth/callback?{urlencode(params)}")


@router.get("/{provider}/login")
def oauth_login(provider: str, request: Request) -> RedirectResponse:
    """
    Initiate OAuth login flow.

    Creates a signed state JWT and redirects the user to the OAuth provider's
    consent screen.

    Args:
        provider: OAuth provider name ("google" or "github")
        request: The incoming request
    """
    if provider not in OAUTH_PROVIDERS:
        frontend_url = _get_frontend_url(request)
        return _redirect_frontend_error(frontend_url, "oauth_failed")

    client_id = _get_client_id(provider)
    if not client_id:
        frontend_url = _get_frontend_url(request)
        return _redirect_frontend_error(frontend_url, "oauth_failed")

    state = _create_oauth_state(action="login", provider=provider)
    config = OAUTH_PROVIDERS[provider]
    callback_url = _get_callback_url(request, provider)

    params = {
        "client_id": client_id,
        "redirect_uri": callback_url,
        "state": state,
        "scope": config["scopes"],
    }
    if provider == "google":
        params["response_type"] = "code"
        params["access_type"] = "offline"

    return RedirectResponse(url=f"{config['authorize_url']}?{urlencode(params)}")


@router.get("/{provider}/register")
def oauth_register(
    provider: str,
    request: Request,
    invitation_code: str | None = None,
) -> RedirectResponse:
    """
    Initiate OAuth registration flow.

    Creates a signed state JWT (carrying invitation_code if provided) and
    redirects the user to the OAuth provider's consent screen.

    Args:
        provider: OAuth provider name ("google" or "github")
        request: The incoming request
        invitation_code: Optional invitation code for invitation-only mode
    """
    if provider not in OAUTH_PROVIDERS:
        frontend_url = _get_frontend_url(request)
        return _redirect_frontend_error(frontend_url, "oauth_failed")

    client_id = _get_client_id(provider)
    if not client_id:
        frontend_url = _get_frontend_url(request)
        return _redirect_frontend_error(frontend_url, "oauth_failed")

    state = _create_oauth_state(
        action="register",
        provider=provider,
        invitation_code=invitation_code,
    )
    config = OAUTH_PROVIDERS[provider]
    callback_url = _get_callback_url(request, provider)

    params = {
        "client_id": client_id,
        "redirect_uri": callback_url,
        "state": state,
        "scope": config["scopes"],
    }
    if provider == "google":
        params["response_type"] = "code"
        params["access_type"] = "offline"

    return RedirectResponse(url=f"{config['authorize_url']}?{urlencode(params)}")


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_db_session),
) -> RedirectResponse:
    """
    Handle OAuth provider callback.

    Verifies state, exchanges code for token, gets user email, then either
    registers or logs in the user depending on the action in the state.

    Args:
        provider: OAuth provider name
        request: The incoming request
        code: Authorization code from provider
        state: Signed state JWT
        error: Error from provider (e.g. user denied consent)
        session: Database session
    """
    frontend_url = _get_frontend_url(request)

    # Handle provider-side errors (e.g. user cancelled)
    if error or not code or not state:
        return _redirect_frontend_error(frontend_url, "oauth_failed")

    # Verify state
    state_data = _verify_oauth_state(state)
    if not state_data:
        return _redirect_frontend_error(frontend_url, "oauth_failed")

    if state_data.get("provider") != provider:
        return _redirect_frontend_error(frontend_url, "oauth_failed")

    action = state_data.get("action")  # "login" or "register"
    invitation_code = state_data.get("invitation_code")

    # Exchange code for access token
    callback_url = _get_callback_url(request, provider)
    access_token = await _exchange_code_for_token(provider, code, callback_url)
    if not access_token:
        return _redirect_frontend_error(frontend_url, "oauth_failed")

    # Get user email from provider
    email = await _get_user_email(provider, access_token)
    if not email:
        return _redirect_frontend_error(frontend_url, "oauth_failed")

    email = email.lower().strip()

    if action == "register":
        return _handle_register(session, frontend_url, provider, email, invitation_code)
    if action == "login":
        return _handle_login(session, frontend_url, provider, email)
    return _redirect_frontend_error(frontend_url, "oauth_failed")


def _handle_register(
    session: Session,
    frontend_url: str,
    provider: str,
    email: str,
    invitation_code: str | None,
) -> RedirectResponse:
    """
    Handle OAuth registration callback.

    Args:
        session: Database session
        frontend_url: Frontend base URL
        provider: OAuth provider name
        email: User's email from OAuth
        invitation_code: Optional invitation code
    """
    # Check if email already exists
    existing = get_organization_by_email(session=session, email=email)
    if existing:
        return _redirect_frontend_error(frontend_url, "email_exists")

    # Handle invitation-only mode
    invitation_only = is_invitation_only_enabled()
    if invitation_only:
        if not invitation_code:
            return _redirect_frontend_error(frontend_url, "invitation_required")
        inv = claim_invitation_code(session=session, code=invitation_code, email=email)
        if inv is None:
            return _redirect_frontend_error(frontend_url, "invalid_invitation")

    # Create org (auto-verified, no password)
    try:
        org = register_organization(
            org_email=email,
            password="",
            session=session,
            auth_provider=provider,
        )
    except Exception:
        # Release invitation code if registration fails
        if invitation_only and invitation_code:
            release_invitation_code(session=session, code=invitation_code)
        return _redirect_frontend_error(frontend_url, "oauth_failed")

    # Auto-verify OAuth accounts
    org.is_verified = True  # type: ignore[reportAttributeAccessIssue]
    update_organization(session=session, organization=org)

    # Create API token
    api_key = generate_short_api_key()
    create_api_token(
        session=session,
        org_id=org.id,  # type: ignore[reportArgumentType]
        token_value=api_key,
        name="Default",  # type: ignore[reportArgumentType]
    )

    feature_flags = get_all_feature_flags(str(org.id))
    return _redirect_frontend_success(
        frontend_url, token=api_key, email=email, feature_flags=feature_flags
    )


def _handle_login(
    session: Session,
    frontend_url: str,
    provider: str,
    email: str,
) -> RedirectResponse:
    """
    Handle OAuth login callback.

    Args:
        session: Database session
        frontend_url: Frontend base URL
        provider: OAuth provider name
        email: User's email from OAuth
    """
    org = get_organization_by_email(session=session, email=email)
    if not org:
        return _redirect_frontend_error(frontend_url, "no_account")

    # Check auth_provider matches
    org_provider = getattr(org, "auth_provider", "email") or "email"
    if org_provider != provider:
        return _redirect_frontend_error(frontend_url, "wrong_provider")

    # Check if account is active
    if org.is_active is False:
        return _redirect_frontend_error(frontend_url, "oauth_failed")

    # Get or create API token (same pattern as /token endpoint)
    existing_tokens = get_api_tokens_by_org_id(session=session, org_id=org.id)  # type: ignore[reportArgumentType]
    if existing_tokens:
        api_key = existing_tokens[0].token
    else:
        api_key = generate_short_api_key()
        create_api_token(
            session=session,
            org_id=org.id,  # type: ignore[reportArgumentType]
            token_value=api_key,
            name="Default",  # type: ignore[reportArgumentType]
        )

    feature_flags = get_all_feature_flags(str(org.id))
    return _redirect_frontend_success(
        frontend_url,
        token=api_key,  # type: ignore[reportArgumentType]
        email=email,
        feature_flags=feature_flags,  # type: ignore[reportArgumentType]
    )
