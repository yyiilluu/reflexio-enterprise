from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, Integer, String

from .database import Base


class InvitationCode(Base):
    __tablename__ = "invitation_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)
    is_used = Column(Boolean, default=False)
    used_by_email = Column(String, nullable=True)
    used_at = Column(Integer, nullable=True)
    created_at = Column(Integer, default=lambda: int(datetime.now(UTC).timestamp()))
    expires_at = Column(Integer, nullable=True)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(Integer, default=lambda: int(datetime.now(UTC).timestamp()))
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    interaction_count = Column(Integer, default=0)
    configuration_json = Column(String, default="")
    is_self_managed = Column(Boolean, default=False)
    auth_provider = Column(String(20), default="email")


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, nullable=False, index=True)
    token = Column(String(40), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False, default="Default")
    created_at = Column(Integer, default=lambda: int(datetime.now(UTC).timestamp()))
    last_used_at = Column(Integer, nullable=True)
