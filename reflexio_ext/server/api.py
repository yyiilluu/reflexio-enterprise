"""Enterprise app — wraps the OS create_app() factory with auth + enterprise routers."""

import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from reflexio.server.api import create_app

from reflexio_ext.server.api_endpoints.login import get_current_active_org
from reflexio_ext.server.db.db_operations import get_db_session

# Self-host mode configuration
SELF_HOST_MODE = os.getenv("SELF_HOST", "false").lower() == "true"
DEFAULT_ORG_ID = "self-host-org"

# Optional HTTP Bearer for self-host mode
optional_oauth2_scheme = HTTPBearer(auto_error=False)


def get_optional_db_session() -> object | None:
    """Get database session only if not in self-host mode."""
    if SELF_HOST_MODE:
        return None
    return next(get_db_session())


def enterprise_get_org_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_oauth2_scheme),
) -> str:
    """Get organization ID, either from token or use default for self-host mode.

    Args:
        credentials: Authentication credentials (only required in non-self-host mode)

    Returns:
        str: Organization ID
    """
    if SELF_HOST_MODE:
        return DEFAULT_ORG_ID

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = next(get_db_session())
    try:
        token = credentials.credentials
        current_org = get_current_active_org(token=token, session=session)  # type: ignore[reportArgumentType]
        return str(current_org.id)
    finally:
        if session is not None:
            session.close()


def _build_enterprise_routers() -> list[APIRouter]:
    """Build enterprise-specific API routers (login, oauth, migration)."""
    from reflexio_ext.server.api_endpoints import login, oauth, self_managed_migration

    enterprise_router = APIRouter()

    # Register login endpoints
    if hasattr(login, "register_routes"):
        login.register_routes(enterprise_router)  # type: ignore[reportAttributeAccessIssue]

    # Register oauth endpoints
    if hasattr(oauth, "register_routes"):
        oauth.register_routes(enterprise_router)  # type: ignore[reportAttributeAccessIssue]

    # Register self-managed migration endpoints
    if hasattr(self_managed_migration, "register_routes"):
        self_managed_migration.register_routes(enterprise_router)  # type: ignore[reportAttributeAccessIssue]

    return [enterprise_router]


# Create enterprise app using factory
app = create_app(
    get_org_id=enterprise_get_org_id,
    additional_routers=_build_enterprise_routers(),
)
