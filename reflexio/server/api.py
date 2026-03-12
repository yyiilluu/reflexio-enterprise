import asyncio
import logging
import os
from typing import Annotated, Optional
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import (
    OAuth2PasswordRequestForm,
    HTTPBearer,
    HTTPAuthorizationCredentials,
)
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from reflexio.server.api_endpoints.login import (
    authenticate_organization,
    create_verification_token,
    create_password_reset_token,
    generate_short_api_key,
    get_current_active_org,
    get_password_hash,
    invalidate_org_cache,
    invalidate_token_cache,
    oauth2_scheme,
    register_organization,
    verify_email_token,
    verify_password_reset_token,
)
from reflexio_commons.api_schema.service_schemas import (
    DeleteUserInteractionRequest,
    DeleteUserInteractionResponse,
    DeleteUserProfileRequest,
    DeleteUserProfileResponse,
    DeleteRequestRequest,
    DeleteRequestResponse,
    DeleteSessionRequest,
    DeleteSessionResponse,
    DeleteFeedbackRequest,
    DeleteFeedbackResponse,
    DeleteRawFeedbackRequest,
    DeleteRawFeedbackResponse,
    ProfileChangeLogResponse,
    FeedbackAggregationChangeLogResponse,
    Status,
    PublishUserInteractionRequest,
    PublishUserInteractionResponse,
    AddRawFeedbackRequest,
    AddRawFeedbackResponse,
    AddFeedbackRequest,
    AddFeedbackResponse,
    RunFeedbackAggregationRequest,
    RunFeedbackAggregationResponse,
    RunSkillGenerationRequest,
    RunSkillGenerationResponse,
    UpdateSkillStatusRequest,
    UpdateSkillStatusResponse,
    DeleteSkillRequest,
    DeleteSkillResponse,
    ExportSkillsRequest,
    ExportSkillsResponse,
    RerunProfileGenerationRequest,
    RerunProfileGenerationResponse,
    ManualProfileGenerationRequest,
    ManualProfileGenerationResponse,
    RerunFeedbackGenerationRequest,
    RerunFeedbackGenerationResponse,
    ManualFeedbackGenerationRequest,
    ManualFeedbackGenerationResponse,
    UpgradeProfilesRequest,
    UpgradeProfilesResponse,
    DowngradeProfilesRequest,
    DowngradeProfilesResponse,
    UpgradeRawFeedbacksRequest,
    UpgradeRawFeedbacksResponse,
    DowngradeRawFeedbacksRequest,
    DowngradeRawFeedbacksResponse,
    GetOperationStatusRequest,
    GetOperationStatusResponse,
    CancelOperationRequest,
    CancelOperationResponse,
)
from reflexio_commons.api_schema.retriever_schema import (
    GetInteractionsRequest,
    GetInteractionsResponse,
    GetUserProfilesRequest,
    GetUserProfilesResponse,
    SearchUserProfileRequest,
    SearchUserProfileResponse,
    SearchInteractionRequest,
    SearchInteractionResponse,
    GetRawFeedbacksRequest,
    GetRawFeedbacksResponse,
    GetFeedbacksRequest,
    GetFeedbacksResponse,
    SearchRawFeedbackRequest,
    SearchRawFeedbackResponse,
    SearchFeedbackRequest,
    SearchFeedbackResponse,
    SetConfigResponse,
    GetRequestsRequest,
    GetRequestsResponse,
    UpdateFeedbackStatusRequest,
    UpdateFeedbackStatusResponse,
    GetAgentSuccessEvaluationResultsRequest,
    GetAgentSuccessEvaluationResultsResponse,
    GetDashboardStatsRequest,
    GetDashboardStatsResponse,
    GetProfileStatisticsResponse,
    GetSkillsRequest,
    GetSkillsResponse,
    SearchSkillsRequest,
    SearchSkillsResponse,
    UnifiedSearchRequest,
    UnifiedSearchResponse,
)
from reflexio.server.db.db_operations import (
    get_db_session,
    create_api_token,
    get_api_tokens_by_org_id,
    delete_api_token,
)
from reflexio.server.site_var.feature_flags import (
    get_all_feature_flags,
    is_invitation_only_enabled,
    is_skill_generation_enabled,
)
from reflexio_commons.api_schema.login_schema import (
    Token,
    User,
    VerifyEmailRequest,
    VerifyEmailResponse,
    ResendVerificationRequest,
    ResendVerificationResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    ApiTokenCreateRequest,
    ApiTokenCreateResponse,
    ApiTokenListResponse,
    ApiTokenResponse,
)
from reflexio_commons.config_schema import Config
from reflexio.server.cache.reflexio_cache import (
    get_reflexio,
    invalidate_reflexio_cache,
)
from reflexio.server.api_endpoints import publisher_api, retriever_api
from reflexio.server.services.email.email_service import get_email_service
from reflexio.server.db.db_operations import (
    claim_invitation_code,
    release_invitation_code,
    get_organization_by_email,
    update_organization,
)

logger = logging.getLogger(__name__)

# Bot protection configuration
REQUEST_TIMEOUT_SECONDS = 60
SYNC_REQUEST_TIMEOUT_SECONDS = 600  # Longer timeout for synchronous processing (wait_for_response=true)
SUSPICIOUS_USER_AGENTS = ["bot", "crawler", "spider", "scraper", "curl", "wget"]
ALLOWED_EMPTY_UA_PATHS = ["/health", "/"]  # Paths that allow empty user agents


def get_rate_limit_key(request: Request) -> str:
    """Get rate limit key based on org_id (if authenticated) or IP address.

    Args:
        request (Request): The incoming request

    Returns:
        str: Rate limit key (org_id or IP address)
    """
    if hasattr(request.state, "org_id") and request.state.org_id:
        return f"org:{request.state.org_id}"
    return get_remote_address(request)


# Initialize rate limiter
limiter = Limiter(key_func=get_rate_limit_key)


class BotProtectionMiddleware(BaseHTTPMiddleware):
    """Middleware to detect and block suspicious bot-like requests."""

    async def dispatch(self, request: Request, call_next):
        """Process request and block suspicious patterns.

        Args:
            request (Request): The incoming request
            call_next: Next middleware/handler in chain

        Returns:
            Response: The response from the next handler or a 403 JSON response
        """
        from starlette.responses import JSONResponse

        user_agent = request.headers.get("user-agent", "").lower()
        path = request.url.path

        # Allow health check and root without user agent
        if path not in ALLOWED_EMPTY_UA_PATHS:
            # Block requests with no user agent
            if not user_agent:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Forbidden: Missing user agent"},
                )

            # Block requests with suspicious user agents
            for suspicious in SUSPICIOUS_USER_AGENTS:
                if suspicious in user_agent:
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Forbidden: Suspicious user agent"},
                    )

        return await call_next(request)


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce request timeout."""

    async def dispatch(self, request: Request, call_next):
        """Process request with timeout enforcement.

        Args:
            request (Request): The incoming request
            call_next: Next middleware/handler in chain

        Returns:
            Response: The response from the next handler or a 504 JSON response
        """
        from starlette.responses import JSONResponse

        # Use longer timeout for synchronous processing requests
        timeout = REQUEST_TIMEOUT_SECONDS
        if request.query_params.get("wait_for_response", "").lower() == "true":
            timeout = SYNC_REQUEST_TIMEOUT_SECONDS

        try:
            return await asyncio.wait_for(
                call_next(request), timeout=timeout
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={"detail": "Request timeout"},
            )


app = FastAPI(docs_url="/docs")

# Configure rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add middlewares (order matters: last added = first executed)
# 1. CORS (outermost)
origins = [
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Timeout middleware
app.add_middleware(TimeoutMiddleware)

# 3. Bot protection (innermost, runs first after CORS)
app.add_middleware(BotProtectionMiddleware)

# Self-host mode configuration
SELF_HOST_MODE = os.getenv("SELF_HOST", "false").lower() == "true"
DEFAULT_ORG_ID = "self-host-org"

# Optional HTTP Bearer for self-host mode
optional_oauth2_scheme = HTTPBearer(auto_error=False)


def get_optional_db_session():
    """Get database session only if not in self-host mode."""
    if SELF_HOST_MODE:
        return None
    return next(get_db_session())


def get_org_id_for_self_host(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        optional_oauth2_scheme
    ),
) -> str:
    """Get organization ID, either from token or use default for self-host mode.

    Args:
        credentials (HTTPAuthorizationCredentials, optional): Authentication credentials (only required in non-self-host mode)

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

    # Get database session for authentication
    session = next(get_db_session())
    try:
        token = credentials.credentials
        current_org = get_current_active_org(token=token, session=session)
        return str(current_org.id)
    finally:
        if session is not None:
            session.close()


def require_skill_generation(
    org_id: str = Depends(get_org_id_for_self_host),
) -> str:
    """Dependency that gates skill endpoints behind the skill_generation feature flag.

    Args:
        org_id (str): Organization ID resolved from auth

    Returns:
        str: The org_id if skill generation is enabled

    Raises:
        HTTPException: 403 if skill generation is not enabled for this org
    """
    if not is_skill_generation_enabled(org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Skill generation is not enabled for this organization",
        )
    return org_id


@app.get("/")
def root():
    return {
        "service": "Reflexio API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health_check():
    """Health check endpoint for ECS/container orchestration."""
    return {"status": "healthy"}


@app.post("/api/logout")
def logout_endpoint(
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Invalidate cache on logout.

    Args:
        org_id (str): Organization ID

    Returns:
        dict: Response containing success status
    """
    invalidate_reflexio_cache(org_id=org_id)
    return {"success": True, "message": "Cache invalidated successfully"}


@app.post("/token", response_model=Token, response_model_exclude_none=True)
@limiter.limit("5/minute")  # Strict limit for login attempts
def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
):
    logger.info(f"Logging in for access token for user: {form_data.username}")
    org = authenticate_organization(
        org_email=form_data.username,
        password=form_data.password,
        session=session,
    )
    if not org:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if account is active
    if org.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is inactive",
        )

    # Check if email is verified
    if org.is_verified is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address. Check your inbox for the verification link.",
        )

    # Schedule background migration check for self-managed orgs
    if org.is_self_managed:
        from reflexio.server.api_endpoints.self_managed_migration import (
            check_and_migrate_self_managed_org,
        )

        background_tasks.add_task(
            check_and_migrate_self_managed_org,
            org_id=str(org.id),
        )

    feature_flags = get_all_feature_flags(str(org.id))

    # Look up existing api_tokens for this org
    existing_tokens = get_api_tokens_by_org_id(session=session, org_id=org.id)
    if existing_tokens:
        # Return the first existing token
        api_key = existing_tokens[0].token
    else:
        # No tokens exist — create a default one
        api_key = generate_short_api_key()
        create_api_token(
            session=session,
            org_id=org.id,
            token_value=api_key,
            name="Default",
        )

    return {"api_key": api_key, "token_type": "bearer", "feature_flags": feature_flags}


@app.get("/api/users/", response_model=User, response_model_exclude_none=True)
def get_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_db_session),
):
    current_user = get_current_active_org(token=token, session=session)
    user = User(email=str(current_user.email))
    return user


@app.post("/api/register", response_model=Token, response_model_exclude_none=True)
@limiter.limit("3/minute")  # Strict limit for registration
def register(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
    invitation_code: Optional[str] = Form(None),
):
    invitation_only = is_invitation_only_enabled()

    # Validate and atomically claim invitation code if invitation-only mode is enabled
    if invitation_only:
        if not invitation_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation code is required",
            )
        inv = claim_invitation_code(
            session=session, code=invitation_code, email=form_data.username
        )
        if inv is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid, expired, or already used invitation code",
            )

    api_key = generate_short_api_key()
    try:
        org = register_organization(
            org_email=form_data.username,
            password=form_data.password,
            session=session,
            api_key=api_key,
        )
        # Create the api_token record
        create_api_token(
            session=session,
            org_id=org.id,
            token_value=api_key,
            name="Default",
        )
    except Exception:
        # Release the invitation code if registration fails unexpectedly
        if invitation_only and invitation_code:
            release_invitation_code(session=session, code=invitation_code)
        raise
    if invitation_only:
        # Auto-verify the organization (code already claimed atomically above)
        org.is_verified = True
        update_organization(session=session, organization=org)
        return {
            "api_key": api_key,
            "token_type": "bearer",
            "auto_verified": True,
        }

    # Normal flow: send verification email
    verification_token = create_verification_token(form_data.username)
    email_service = get_email_service()
    background_tasks.add_task(
        email_service.send_verification_email,
        form_data.username,
        verification_token,
    )

    return {"api_key": api_key, "token_type": "bearer"}


def _mask_token(token_value: str) -> str:
    """Mask a token for display: show prefix and last 4 chars."""
    if len(token_value) <= 12:
        return token_value[:4] + "..." + token_value[-4:]
    return token_value[:8] + "..." + token_value[-4:]


@app.get("/api/tokens", response_model=ApiTokenListResponse)
def list_api_tokens(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        optional_oauth2_scheme
    ),
):
    """
    List all API tokens for the current organization. Token values are masked.

    Returns:
        ApiTokenListResponse: List of masked tokens
    """
    if SELF_HOST_MODE:
        return ApiTokenListResponse(tokens=[])

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = next(get_db_session())
    try:
        current_org = get_current_active_org(
            token=credentials.credentials, session=session
        )
        tokens = get_api_tokens_by_org_id(session=session, org_id=current_org.id)
        return ApiTokenListResponse(
            tokens=[
                ApiTokenResponse(
                    id=t.id,
                    name=t.name,
                    token_masked=_mask_token(t.token),
                    created_at=t.created_at,
                    last_used_at=t.last_used_at,
                )
                for t in tokens
            ]
        )
    finally:
        if session is not None:
            session.close()


@app.post("/api/tokens", response_model=ApiTokenCreateResponse)
def create_new_api_token(
    payload: ApiTokenCreateRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        optional_oauth2_scheme
    ),
):
    """
    Create a new API token for the current organization.
    Returns the full token value — it is only shown once.

    Args:
        payload: Token creation request with name

    Returns:
        ApiTokenCreateResponse: The newly created token (full value shown once)
    """
    if SELF_HOST_MODE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token management not available in self-host mode",
        )

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = next(get_db_session())
    try:
        current_org = get_current_active_org(
            token=credentials.credentials, session=session
        )
        new_token_value = generate_short_api_key()
        api_token = create_api_token(
            session=session,
            org_id=current_org.id,
            token_value=new_token_value,
            name=payload.name,
        )
        return ApiTokenCreateResponse(
            id=api_token.id,
            name=api_token.name,
            token=api_token.token,
            created_at=api_token.created_at,
        )
    finally:
        if session is not None:
            session.close()


@app.delete("/api/tokens/{token_id}")
def delete_api_token_endpoint(
    token_id: int,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        optional_oauth2_scheme
    ),
):
    """
    Delete an API token by ID.

    Args:
        token_id: ID of the token to delete

    Returns:
        dict: Success status
    """
    if SELF_HOST_MODE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token management not available in self-host mode",
        )

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = next(get_db_session())
    try:
        current_org = get_current_active_org(
            token=credentials.credentials, session=session
        )
        # Prevent deleting the last token
        existing_tokens = get_api_tokens_by_org_id(
            session=session, org_id=current_org.id
        )
        if len(existing_tokens) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the last API token. Create a new one first.",
            )

        deleted = delete_api_token(
            session=session, token_id=token_id, org_id=current_org.id
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found",
            )

        # Invalidate cache for the deleted token
        for t in existing_tokens:
            if t.id == token_id:
                invalidate_token_cache(t.token)
                break

        return {"success": True, "message": "Token deleted"}
    finally:
        if session is not None:
            session.close()


@app.post("/api/verify-email", response_model=VerifyEmailResponse)
@limiter.limit("10/minute")
def verify_email(
    request: Request,
    payload: VerifyEmailRequest,
    session: Session = Depends(get_db_session),
):
    """
    Verify a user's email address using the verification token.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (VerifyEmailRequest): The verification token
        session (Session): Database session

    Returns:
        VerifyEmailResponse: Success status and message
    """
    # Verify the token
    email = verify_email_token(payload.token)
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    # Get the organization
    org = get_organization_by_email(session=session, email=email)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    # Check if already verified
    if org.is_verified:
        return VerifyEmailResponse(success=True, message="Email already verified")

    # Update verification status
    org.is_verified = True
    update_organization(session=session, organization=org)

    # Invalidate cache to ensure fresh data on next login
    invalidate_org_cache(email)

    return VerifyEmailResponse(success=True, message="Email verified successfully")


@app.post("/api/resend-verification", response_model=ResendVerificationResponse)
@limiter.limit("2/minute")  # Strict limit to prevent abuse
def resend_verification_email(
    request: Request,
    payload: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
):
    """
    Resend verification email to a user.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (ResendVerificationRequest): The email address
        background_tasks (BackgroundTasks): Background task runner
        session (Session): Database session

    Returns:
        ResendVerificationResponse: Success status and message
    """
    # Get the organization (but don't reveal if it exists for security)
    org = get_organization_by_email(session=session, email=payload.email)

    # Always return success to prevent email enumeration
    generic_message = (
        "If an unverified account exists with this email, "
        "a verification link has been sent"
    )

    if org is None or org.is_verified:
        return ResendVerificationResponse(success=True, message=generic_message)

    # Send verification email
    verification_token = create_verification_token(payload.email)
    email_service = get_email_service()
    background_tasks.add_task(
        email_service.send_verification_email,
        payload.email,
        verification_token,
    )

    return ResendVerificationResponse(success=True, message=generic_message)


@app.post("/api/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit("3/minute")  # Strict limit to prevent abuse
def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
):
    """
    Request a password reset email.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (ForgotPasswordRequest): The email address
        background_tasks (BackgroundTasks): Background task runner
        session (Session): Database session

    Returns:
        ForgotPasswordResponse: Always returns success to prevent email enumeration
    """
    # Get the organization (but don't reveal if it exists for security)
    org = get_organization_by_email(session=session, email=payload.email)

    # Always return success to prevent email enumeration
    generic_message = (
        "If an account exists with this email, " "a password reset link has been sent"
    )

    # Only send email if account exists
    if org is not None:
        reset_token = create_password_reset_token(payload.email)
        email_service = get_email_service()
        background_tasks.add_task(
            email_service.send_password_reset_email,
            payload.email,
            reset_token,
        )

    return ForgotPasswordResponse(success=True, message=generic_message)


@app.post("/api/reset-password", response_model=ResetPasswordResponse)
@limiter.limit("5/minute")  # Strict limit to prevent brute force
def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    session: Session = Depends(get_db_session),
):
    """
    Reset password using a valid reset token.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (ResetPasswordRequest): The reset token and new password
        session (Session): Database session

    Returns:
        ResetPasswordResponse: Success status and message
    """
    # Verify the token
    email = verify_password_reset_token(payload.token)
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    # Validate new password (minimum 6 characters)
    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters",
        )

    # Get the organization
    org = get_organization_by_email(session=session, email=email)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    # Update password
    org.hashed_password = get_password_hash(payload.new_password)
    update_organization(session=session, organization=org)

    # Invalidate cache to ensure fresh data on next login
    invalidate_org_cache(email)

    return ResetPasswordResponse(success=True, message="Password reset successfully")


@app.post(
    "/api/publish_interaction",
    response_model=PublishUserInteractionResponse,
    response_model_exclude_none=True,
)
@limiter.limit("60/minute")  # Rate limit for write operations
def publish_user_interaction(
    request: Request,
    payload: PublishUserInteractionRequest,
    background_tasks: BackgroundTasks,
    org_id: str = Depends(get_org_id_for_self_host),
    wait_for_response: bool = False,
):
    if wait_for_response:
        # Process synchronously so the caller gets the real result
        return publisher_api.add_user_interaction(org_id=org_id, request=payload)
    else:
        # Run in background — caller gets immediate acknowledgement
        background_tasks.add_task(
            publisher_api.add_user_interaction, org_id=org_id, request=payload
        )
        return PublishUserInteractionResponse(
            success=True, message="Interaction queued for processing"
        )


@app.post(
    "/api/add_raw_feedback",
    response_model=AddRawFeedbackResponse,
    response_model_exclude_none=True,
)
@limiter.limit("60/minute")  # Rate limit for write operations
def add_raw_feedback_endpoint(
    request: Request,
    payload: AddRawFeedbackRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Add raw feedback directly to storage.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (AddRawFeedbackRequest): The request containing raw feedbacks
        org_id (str): Organization ID

    Returns:
        AddRawFeedbackResponse: Response containing success status, message, and added count
    """
    return publisher_api.add_raw_feedback(org_id=org_id, request=payload)


@app.post(
    "/api/add_feedbacks",
    response_model=AddFeedbackResponse,
    response_model_exclude_none=True,
)
@limiter.limit("60/minute")  # Rate limit for write operations
def add_feedback_endpoint(
    request: Request,
    payload: AddFeedbackRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Add aggregated feedback directly to storage.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (AddFeedbackRequest): The request containing feedbacks
        org_id (str): Organization ID

    Returns:
        AddFeedbackResponse: Response containing success status, message, and added count
    """
    return publisher_api.add_feedback(org_id=org_id, request=payload)


@app.post(
    "/api/search_profiles",
    response_model=SearchUserProfileResponse,
    response_model_exclude_none=True,
)
@limiter.limit("120/minute")  # Rate limit for read operations
def search_profiles(
    request: Request,
    payload: SearchUserProfileRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    return retriever_api.search_user_profiles(org_id=org_id, request=payload)


@app.post(
    "/api/search_interactions",
    response_model=SearchInteractionResponse,
    response_model_exclude_none=True,
)
@limiter.limit("120/minute")  # Rate limit for read operations
def search_interactions(
    request: Request,
    payload: SearchInteractionRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    return retriever_api.search_interactions(org_id=org_id, request=payload)


@app.post(
    "/api/search_raw_feedbacks",
    response_model=SearchRawFeedbackResponse,
    response_model_exclude_none=True,
)
@limiter.limit("120/minute")  # Rate limit for read operations
def search_raw_feedbacks_endpoint(
    request: Request,
    payload: SearchRawFeedbackRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Search raw feedbacks with semantic search and advanced filtering.

    Supports filtering by user_id (via request_id linkage), agent_version,
    feedback_name, datetime range, and status.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (SearchRawFeedbackRequest): The search request
        org_id (str): Organization ID

    Returns:
        SearchRawFeedbackResponse: Response containing matching raw feedbacks
    """
    response = retriever_api.search_raw_feedbacks(org_id=org_id, request=payload)
    # Filter out embedding fields
    for raw_feedback in response.raw_feedbacks:
        raw_feedback.embedding = []
    return response


@app.post(
    "/api/search_feedbacks",
    response_model=SearchFeedbackResponse,
    response_model_exclude_none=True,
)
@limiter.limit("120/minute")  # Rate limit for read operations
def search_feedbacks_endpoint(
    request: Request,
    payload: SearchFeedbackRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Search aggregated feedbacks with semantic search and advanced filtering.

    Supports filtering by agent_version, feedback_name, datetime range,
    status_filter, and feedback_status_filter.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (SearchFeedbackRequest): The search request
        org_id (str): Organization ID

    Returns:
        SearchFeedbackResponse: Response containing matching feedbacks
    """
    response = retriever_api.search_feedbacks(org_id=org_id, request=payload)
    # Filter out embedding fields
    for feedback in response.feedbacks:
        feedback.embedding = []
    return response


@app.post(
    "/api/search",
    response_model=UnifiedSearchResponse,
    response_model_exclude_none=True,
)
@limiter.limit("120/minute")
def unified_search_endpoint(
    request: Request,
    payload: UnifiedSearchRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Search across all entity types (profiles, feedbacks, raw_feedbacks, skills).

    Runs query rewriting and embedding generation in parallel, then searches
    all entity types in parallel. Query rewriting is gated behind the
    query_rewrite feature flag. Skills are only searched if the
    skill_generation feature flag is enabled for the org.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (UnifiedSearchRequest): The unified search request
        org_id (str): Organization ID

    Returns:
        UnifiedSearchResponse: Combined search results
    """
    response = retriever_api.unified_search(org_id=org_id, request=payload)
    # Filter out embedding fields
    for profile in response.profiles:
        profile.embedding = []
    for feedback in response.feedbacks:
        feedback.embedding = []
    for raw_feedback in response.raw_feedbacks:
        raw_feedback.embedding = []
    return response


@app.get("/api/profile_change_log", response_model=ProfileChangeLogResponse)
def get_profile_change_log(
    org_id: str = Depends(get_org_id_for_self_host),
):
    return retriever_api.get_profile_change_logs(org_id=org_id)


@app.get(
    "/api/feedback_aggregation_change_logs",
    response_model=FeedbackAggregationChangeLogResponse,
)
def get_feedback_aggregation_change_logs(
    feedback_name: str,
    agent_version: str,
    org_id: str = Depends(get_org_id_for_self_host),
):
    return retriever_api.get_feedback_aggregation_change_logs(
        org_id=org_id,
        feedback_name=feedback_name,
        agent_version=agent_version,
    )


@app.delete(
    "/api/delete_profile",
    response_model=DeleteUserProfileResponse,
    response_model_exclude_none=True,
)
def delete_profile(
    request: DeleteUserProfileRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    return publisher_api.delete_user_profile(org_id=org_id, request=request)


@app.delete(
    "/api/delete_interaction",
    response_model=DeleteUserInteractionResponse,
    response_model_exclude_none=True,
)
def delete_interaction(
    request: DeleteUserInteractionRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    return publisher_api.delete_user_interaction(org_id=org_id, request=request)


@app.delete(
    "/api/delete_request",
    response_model=DeleteRequestResponse,
    response_model_exclude_none=True,
)
def delete_request(
    request: DeleteRequestRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    return publisher_api.delete_request(org_id=org_id, request=request)


@app.delete(
    "/api/delete_session",
    response_model=DeleteSessionResponse,
    response_model_exclude_none=True,
)
def delete_session(
    request: DeleteSessionRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    return publisher_api.delete_session(org_id=org_id, request=request)


@app.delete(
    "/api/delete_feedback",
    response_model=DeleteFeedbackResponse,
    response_model_exclude_none=True,
)
def delete_feedback(
    request: DeleteFeedbackRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    return publisher_api.delete_feedback(org_id=org_id, request=request)


@app.delete(
    "/api/delete_raw_feedback",
    response_model=DeleteRawFeedbackResponse,
    response_model_exclude_none=True,
)
def delete_raw_feedback(
    request: DeleteRawFeedbackRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    return publisher_api.delete_raw_feedback(org_id=org_id, request=request)


@app.post(
    "/api/get_interactions",
    response_model=GetInteractionsResponse,
    response_model_exclude_none=True,
)
def get_interactions(
    request: GetInteractionsRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    return retriever_api.get_user_interactions(org_id=org_id, request=request)


@app.get(
    "/api/get_all_interactions",
    response_model=GetInteractionsResponse,
    response_model_exclude_none=True,
)
def get_all_interactions(
    limit: int = 100,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Get all user interactions across all users.

    Args:
        limit (int, optional): Maximum number of interactions to return. Defaults to 100.
        org_id (str): Organization ID

    Returns:
        GetInteractionsResponse: Response containing all user interactions
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Get all interactions using Reflexio's get_all_interactions method
    response = reflexio.get_all_interactions(limit=limit)

    # Filter out embedding fields from interactions
    for interaction in response.interactions:
        interaction.embedding = []

    return response


@app.post(
    "/api/get_requests",
    response_model=GetRequestsResponse,
    response_model_exclude_none=True,
)
def get_requests_endpoint(
    request: GetRequestsRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Get requests with their associated interactions.

    Args:
        request (GetRequestsRequest): The get request
        org_id (str): Organization ID

    Returns:
        GetRequestsResponse: Response containing requests with their interactions
    """
    return retriever_api.get_requests(org_id=org_id, request=request)


@app.post(
    "/api/get_profiles",
    response_model=GetUserProfilesResponse,
    response_model_exclude_none=True,
)
def get_profiles(
    request: GetUserProfilesRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    return retriever_api.get_user_profiles(org_id=org_id, request=request)


@app.get(
    "/api/get_all_profiles",
    response_model=GetUserProfilesResponse,
    response_model_exclude_none=True,
)
def get_all_profiles(
    limit: int = 100,
    status_filter: Optional[str] = None,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Get all user profiles across all users.

    Args:
        limit (int, optional): Maximum number of profiles to return. Defaults to 100.
        status_filter (str, optional): Filter by profile status. Can be "current", "pending", or "archived".
        org_id (str): Organization ID

    Returns:
        GetUserProfilesResponse: Response containing all user profiles
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Map status_filter string to Status list
    status_filter_list = None
    if status_filter == "current":
        status_filter_list = [None]
    elif status_filter == "pending":
        status_filter_list = [Status.PENDING]
    elif status_filter == "archived":
        status_filter_list = [Status.ARCHIVED]

    # Get all profiles using Reflexio's get_all_profiles method
    response = reflexio.get_all_profiles(limit=limit, status_filter=status_filter_list)

    # Filter out embedding fields from profiles
    for profile in response.user_profiles:
        profile.embedding = []

    return response


@app.get(
    "/api/get_profile_statistics",
    response_model=GetProfileStatisticsResponse,
    response_model_exclude_none=True,
)
def get_profile_statistics(
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Get efficient profile statistics using storage layer queries.

    Args:
        org_id (str): Organization ID

    Returns:
        GetProfileStatisticsResponse: Response containing profile counts by status
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Get profile statistics using Reflexio's method
    response = reflexio.get_profile_statistics()

    return response


@app.post(
    "/api/run_feedback_aggregation",
    response_model=RunFeedbackAggregationResponse,
    response_model_exclude_none=True,
)
@limiter.limit("10/minute")  # Strict limit for expensive operations
def run_feedback_aggregation(
    request: Request,
    payload: RunFeedbackAggregationRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    return publisher_api.run_feedback_aggregation(org_id=org_id, request=payload)


@app.post(
    "/api/run_skill_generation",
    response_model=RunSkillGenerationResponse,
    response_model_exclude_none=True,
)
@limiter.limit("5/minute")
def run_skill_generation(
    request: Request,
    payload: RunSkillGenerationRequest,
    org_id: str = Depends(require_skill_generation),
):
    return publisher_api.run_skill_generation(org_id=org_id, request=payload)


@app.post(
    "/api/get_skills",
    response_model=GetSkillsResponse,
    response_model_exclude_none=True,
)
@limiter.limit("120/minute")
def get_skills(
    request: Request,
    payload: GetSkillsRequest,
    org_id: str = Depends(require_skill_generation),
):
    reflexio = get_reflexio(org_id)
    skills = reflexio.get_skills(
        limit=payload.limit or 100,
        feedback_name=payload.feedback_name,
        agent_version=payload.agent_version,
        skill_status=payload.skill_status,
    )
    return GetSkillsResponse(success=True, skills=skills)


@app.post(
    "/api/search_skills",
    response_model=SearchSkillsResponse,
    response_model_exclude_none=True,
)
@limiter.limit("120/minute")
def search_skills(
    request: Request,
    payload: SearchSkillsRequest,
    org_id: str = Depends(require_skill_generation),
):
    reflexio = get_reflexio(org_id)
    skills = reflexio.search_skills(
        query=payload.query,
        feedback_name=payload.feedback_name,
        agent_version=payload.agent_version,
        skill_status=payload.skill_status,
        threshold=payload.threshold or 0.5,
        count=payload.top_k or 10,
    )
    return SearchSkillsResponse(success=True, skills=skills)


@app.post(
    "/api/update_skill_status",
    response_model=UpdateSkillStatusResponse,
    response_model_exclude_none=True,
)
@limiter.limit("60/minute")
def update_skill_status(
    request: Request,
    payload: UpdateSkillStatusRequest,
    org_id: str = Depends(require_skill_generation),
):
    reflexio = get_reflexio(org_id)
    try:
        reflexio.update_skill_status(payload.skill_id, payload.skill_status)
    except Exception as e:
        return UpdateSkillStatusResponse(success=False, message=str(e))
    return UpdateSkillStatusResponse(success=True)


@app.delete(
    "/api/delete_skill",
    response_model=DeleteSkillResponse,
    response_model_exclude_none=True,
)
@limiter.limit("60/minute")
def delete_skill(
    request: Request,
    payload: DeleteSkillRequest,
    org_id: str = Depends(require_skill_generation),
):
    reflexio = get_reflexio(org_id)
    try:
        reflexio.delete_skill(payload.skill_id)
    except Exception as e:
        return DeleteSkillResponse(success=False, message=str(e))
    return DeleteSkillResponse(success=True)


@app.post(
    "/api/export_skills",
    response_model=ExportSkillsResponse,
    response_model_exclude_none=True,
)
@limiter.limit("30/minute")
def export_skills(
    request: Request,
    payload: ExportSkillsRequest,
    org_id: str = Depends(require_skill_generation),
):
    reflexio = get_reflexio(org_id)
    try:
        markdown = reflexio.export_skills(
            feedback_name=payload.feedback_name,
            agent_version=payload.agent_version,
            skill_status=payload.skill_status,
        )
    except Exception as e:
        return ExportSkillsResponse(success=False, msg=str(e))
    return ExportSkillsResponse(success=True, markdown=markdown)


@app.post("/api/set_config")
def set_config(
    config: Config,
    org_id: str = Depends(get_org_id_for_self_host),
) -> SetConfigResponse:
    """Set configuration for the organization.

    Args:
        config (Config): The configuration to set
        org_id (str): Organization ID

    Returns:
        dict: Response containing success status and message
    """
    # Create Reflexio instance to access the configurator through request_context
    reflexio = get_reflexio(org_id=org_id)

    # Set the config using Reflexio's set_config method
    response = reflexio.set_config(config)

    # Invalidate cache on successful config change to ensure fresh instance next request
    if response.success:
        invalidate_reflexio_cache(org_id=org_id)

    return response


@app.get("/api/get_config", response_model=Config)
def get_config(
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Get configuration for the organization.

    Args:
        org_id (str): Organization ID

    Returns:
        Config: The current configuration
    """
    # Create Reflexio instance to access the configurator through request_context
    reflexio = get_reflexio(org_id=org_id)

    # Get the config using Reflexio's get_config method
    return reflexio.get_config()


@app.post(
    "/api/get_raw_feedbacks",
    response_model=GetRawFeedbacksResponse,
    response_model_exclude_none=True,
)
def get_raw_feedbacks(
    request: GetRawFeedbacksRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Get raw feedbacks with embeddings filtered out.

    Args:
        request (GetRawFeedbacksRequest): The get request
        org_id (str): Organization ID

    Returns:
        GetRawFeedbacksResponse: Response containing raw feedbacks without embeddings
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Get raw feedbacks using Reflexio's get_raw_feedbacks method
    response = reflexio.get_raw_feedbacks(request)

    # Filter out embedding fields from raw_feedbacks
    for raw_feedback in response.raw_feedbacks:
        raw_feedback.embedding = []

    return response


@app.post(
    "/api/get_feedbacks",
    response_model=GetFeedbacksResponse,
    response_model_exclude_none=True,
)
def get_feedbacks(
    request: GetFeedbacksRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Get feedbacks with embeddings filtered out.

    Args:
        request (GetFeedbacksRequest): The get request
        org_id (str): Organization ID

    Returns:
        GetFeedbacksResponse: Response containing feedbacks without embeddings
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Get feedbacks using Reflexio's get_feedbacks method
    response = reflexio.get_feedbacks(request)

    # Filter out embedding fields from feedbacks
    for feedback in response.feedbacks:
        feedback.embedding = []

    return response


@app.post(
    "/api/get_agent_success_evaluation_results",
    response_model=GetAgentSuccessEvaluationResultsResponse,
    response_model_exclude_none=True,
)
def get_agent_success_evaluation_results(
    request: GetAgentSuccessEvaluationResultsRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Get agent success evaluation results.

    Args:
        request (GetAgentSuccessEvaluationResultsRequest): The get request
        org_id (str): Organization ID

    Returns:
        GetAgentSuccessEvaluationResultsResponse: Response containing agent success evaluation results
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Get agent success evaluation results using Reflexio's method
    response = reflexio.get_agent_success_evaluation_results(request)

    return response


@app.put(
    "/api/update_feedback_status",
    response_model=UpdateFeedbackStatusResponse,
    response_model_exclude_none=True,
)
def update_feedback_status_endpoint(
    request: UpdateFeedbackStatusRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Update the status of a specific feedback.

    Args:
        request (UpdateFeedbackStatusRequest): The update request
        org_id (str): Organization ID

    Returns:
        UpdateFeedbackStatusResponse: Response containing success status and message
    """
    return publisher_api.update_feedback_status(org_id=org_id, request=request)


@app.post(
    "/api/get_dashboard_stats",
    response_model=GetDashboardStatsResponse,
    response_model_exclude_none=True,
)
def get_dashboard_stats(
    request: GetDashboardStatsRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Get comprehensive dashboard statistics including counts and time-series data.

    Args:
        request (GetDashboardStatsRequest): Request containing days_back and granularity
        org_id (str): Organization ID

    Returns:
        GetDashboardStatsResponse: Response containing dashboard statistics
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Get dashboard stats using Reflexio's method
    response = reflexio.get_dashboard_stats(request)

    return response


@app.post(
    "/api/rerun_profile_generation",
    response_model=RerunProfileGenerationResponse,
    response_model_exclude_none=True,
)
@limiter.limit("5/minute")  # Strict limit for expensive operations
def rerun_profile_generation_endpoint(
    request: Request,
    payload: RerunProfileGenerationRequest,
    background_tasks: BackgroundTasks,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Rerun profile generation for a user with filtered interactions.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (RerunProfileGenerationRequest): Request containing user_id, time filters, and source
        background_tasks (BackgroundTasks): Background task runner
        org_id (str): Organization ID

    Returns:
        RerunProfileGenerationResponse: Response containing success status and profiles generated count
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Run the long-running task in the background to avoid proxy timeout
    # Client polls get_operation_status for progress
    background_tasks.add_task(reflexio.rerun_profile_generation, payload)

    return RerunProfileGenerationResponse(
        success=True, msg="Profile generation started"
    )


@app.post(
    "/api/manual_profile_generation",
    response_model=ManualProfileGenerationResponse,
    response_model_exclude_none=True,
)
@limiter.limit("5/minute")  # Strict limit for expensive operations
def manual_profile_generation_endpoint(
    request: Request,
    payload: ManualProfileGenerationRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Manually trigger profile generation with window-sized interactions and CURRENT output.

    This behaves like regular generation (uses extraction_window_size from config,
    outputs CURRENT profiles) but only runs profile extraction.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (ManualProfileGenerationRequest): Request containing user_id, source, and extractor_names
        org_id (str): Organization ID

    Returns:
        ManualProfileGenerationResponse: Response containing success status and profiles generated count
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Call manual_profile_generation
    response = reflexio.manual_profile_generation(payload)

    return response


@app.post(
    "/api/rerun_feedback_generation",
    response_model=RerunFeedbackGenerationResponse,
    response_model_exclude_none=True,
)
@limiter.limit("5/minute")  # Strict limit for expensive operations
def rerun_feedback_generation_endpoint(
    request: Request,
    payload: RerunFeedbackGenerationRequest,
    background_tasks: BackgroundTasks,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Rerun feedback generation with filtered interactions.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (RerunFeedbackGenerationRequest): Request containing agent_version, time filters, and optional feedback_name
        background_tasks (BackgroundTasks): Background task runner
        org_id (str): Organization ID

    Returns:
        RerunFeedbackGenerationResponse: Response containing success status and feedbacks generated count
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Run the long-running task in the background to avoid proxy timeout
    # Client polls get_operation_status for progress
    background_tasks.add_task(reflexio.rerun_feedback_generation, payload)

    return RerunFeedbackGenerationResponse(
        success=True, msg="Feedback generation started"
    )


@app.post(
    "/api/manual_feedback_generation",
    response_model=ManualFeedbackGenerationResponse,
    response_model_exclude_none=True,
)
@limiter.limit("5/minute")  # Strict limit for expensive operations
def manual_feedback_generation_endpoint(
    request: Request,
    payload: ManualFeedbackGenerationRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Manually trigger feedback generation with window-sized interactions and CURRENT output.

    This behaves like regular generation (uses extraction_window_size from config,
    outputs CURRENT feedbacks) but only runs feedback extraction.

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (ManualFeedbackGenerationRequest): Request containing agent_version, source, and feedback_name
        org_id (str): Organization ID

    Returns:
        ManualFeedbackGenerationResponse: Response containing success status and feedbacks generated count
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Call manual_feedback_generation
    response = reflexio.manual_feedback_generation(payload)

    return response


@app.post(
    "/api/upgrade_all_profiles",
    response_model=UpgradeProfilesResponse,
    response_model_exclude_none=True,
)
def upgrade_all_profiles_endpoint(
    request: UpgradeProfilesRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Upgrade all profiles by deleting old ARCHIVED, archiving CURRENT, and promoting PENDING.

    This operation performs three atomic steps:
    1. Delete all ARCHIVED profiles (old archived profiles from previous upgrades)
    2. Archive all CURRENT profiles → ARCHIVED (save current state for potential rollback)
    3. Promote all PENDING profiles → CURRENT (activate new profiles)

    Args:
        request (UpgradeProfilesRequest): The upgrade request with only_affected_users parameter
        org_id (str): Organization ID

    Returns:
        UpgradeProfilesResponse: Response containing success status and counts
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Call upgrade_all_profiles with request
    response = reflexio.upgrade_all_profiles(request=request)

    return response


@app.post(
    "/api/downgrade_all_profiles",
    response_model=DowngradeProfilesResponse,
    response_model_exclude_none=True,
)
def downgrade_all_profiles_endpoint(
    request: DowngradeProfilesRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Downgrade all profiles by demoting CURRENT to PENDING and restoring ARCHIVED.

    This operation performs two atomic steps:
    1. Demote all CURRENT profiles → PENDING
    2. Restore all ARCHIVED profiles → CURRENT

    Args:
        request (DowngradeProfilesRequest): The downgrade request with only_affected_users parameter
        org_id (str): Organization ID

    Returns:
        DowngradeProfilesResponse: Response containing success status and counts
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Call downgrade_all_profiles with request
    response = reflexio.downgrade_all_profiles(request=request)

    return response


@app.post(
    "/api/upgrade_all_raw_feedbacks",
    response_model=UpgradeRawFeedbacksResponse,
    response_model_exclude_none=True,
)
def upgrade_all_raw_feedbacks_endpoint(
    request: UpgradeRawFeedbacksRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Upgrade all raw feedbacks by deleting old ARCHIVED, archiving CURRENT, and promoting PENDING.

    This operation performs three atomic steps:
    1. Delete all ARCHIVED raw feedbacks (old archived from previous upgrades)
    2. Archive all CURRENT raw feedbacks → ARCHIVED (save current state for potential rollback)
    3. Promote all PENDING raw feedbacks → CURRENT (activate new raw feedbacks)

    Args:
        request (UpgradeRawFeedbacksRequest): The upgrade request with optional agent_version and feedback_name filters
        org_id (str): Organization ID

    Returns:
        UpgradeRawFeedbacksResponse: Response containing success status and counts
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Call upgrade_all_raw_feedbacks with request
    response = reflexio.upgrade_all_raw_feedbacks(request=request)

    return response


@app.post(
    "/api/downgrade_all_raw_feedbacks",
    response_model=DowngradeRawFeedbacksResponse,
    response_model_exclude_none=True,
)
def downgrade_all_raw_feedbacks_endpoint(
    request: DowngradeRawFeedbacksRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Downgrade all raw feedbacks by archiving CURRENT and restoring ARCHIVED.

    This operation performs three atomic steps:
    1. Mark all CURRENT raw feedbacks → ARCHIVE_IN_PROGRESS (temporary status)
    2. Restore all ARCHIVED raw feedbacks → CURRENT
    3. Move all ARCHIVE_IN_PROGRESS raw feedbacks → ARCHIVED

    Args:
        request (DowngradeRawFeedbacksRequest): The downgrade request with optional agent_version and feedback_name filters
        org_id (str): Organization ID

    Returns:
        DowngradeRawFeedbacksResponse: Response containing success status and counts
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Call downgrade_all_raw_feedbacks with request
    response = reflexio.downgrade_all_raw_feedbacks(request=request)

    return response


@app.get(
    "/api/get_operation_status",
    response_model=GetOperationStatusResponse,
    response_model_exclude_none=True,
)
def get_operation_status_endpoint(
    service_name: str = "profile_generation",
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Get the status of an operation (e.g., profile generation rerun or manual).

    Args:
        service_name (str): The service name to query. Defaults to "profile_generation"
        org_id (str): Organization ID

    Returns:
        GetOperationStatusResponse: Response containing operation status info
    """
    # Create Reflexio instance
    reflexio = get_reflexio(org_id=org_id)

    # Get operation status
    request = GetOperationStatusRequest(service_name=service_name)
    response = reflexio.get_operation_status(request)

    return response


@app.post(
    "/api/cancel_operation",
    response_model=CancelOperationResponse,
    response_model_exclude_none=True,
)
@limiter.limit("10/minute")
def cancel_operation_endpoint(
    request: Request,
    payload: CancelOperationRequest,
    org_id: str = Depends(get_org_id_for_self_host),
):
    """Cancel an in-progress operation (rerun or manual generation).

    Args:
        request (Request): The HTTP request object (for rate limiting)
        payload (CancelOperationRequest): Request containing optional service_name
        org_id (str): Organization ID

    Returns:
        CancelOperationResponse: Response with list of services that were cancelled
    """
    reflexio = get_reflexio(org_id=org_id)
    return reflexio.cancel_operation(payload)
