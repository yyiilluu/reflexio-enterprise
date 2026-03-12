from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from reflexio_commons.api_schema.validators import NonEmptyStr


class Token(BaseModel):
    api_key: NonEmptyStr
    token_type: NonEmptyStr
    feature_flags: Optional[dict[str, bool]] = None
    auto_verified: Optional[bool] = None


class ApiTokenResponse(BaseModel):
    id: int
    name: str
    token_masked: str
    created_at: Optional[int] = None
    last_used_at: Optional[int] = None


class ApiTokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255, default="Default")


class ApiTokenCreateResponse(BaseModel):
    id: int
    name: str
    token: str
    created_at: Optional[int] = None


class ApiTokenListResponse(BaseModel):
    tokens: list[ApiTokenResponse]


class User(BaseModel):
    email: EmailStr


# Email verification models
class VerifyEmailRequest(BaseModel):
    token: NonEmptyStr


class VerifyEmailResponse(BaseModel):
    success: bool
    message: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ResendVerificationResponse(BaseModel):
    success: bool
    message: str


# Password reset models
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    success: bool
    message: str


class ResetPasswordRequest(BaseModel):
    token: NonEmptyStr
    new_password: str = Field(min_length=1)


class ResetPasswordResponse(BaseModel):
    success: bool
    message: str
