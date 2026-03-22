"""
Comprehensive unit tests for reflexio_ext.server.db.db_operations module.

Tests cover all three storage backends (SQLAlchemy, Supabase, S3) via mocking,
plus edge cases and error handling for every public function.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from reflexio_ext.server.db import db_models

# ---------------------------------------------------------------------------
# Patch targets (module-level symbols inside db_operations)
# ---------------------------------------------------------------------------
_MOD = "reflexio_ext.server.db.db_operations"
_IS_S3 = f"{_MOD}._is_self_host_s3_mode"
_GET_S3 = f"{_MOD}.get_s3_org_storage"
_GET_SB = f"{_MOD}.get_login_supabase_client"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org(
    *,
    id_: int = 1,
    email: str = "test@example.com",
    hashed_password: str = "hashed_pw",
    is_active: bool = True,
    is_verified: bool = False,
    interaction_count: int = 0,
    configuration_json: str = "",
    auth_provider: str = "email",
    created_at: int = 1700000000,
) -> db_models.Organization:
    org = db_models.Organization()
    org.id = id_  # type: ignore[reportAttributeAccessIssue]
    org.email = email  # type: ignore[reportAttributeAccessIssue]
    org.hashed_password = hashed_password  # type: ignore[reportAttributeAccessIssue]
    org.is_active = is_active
    org.is_verified = is_verified
    org.interaction_count = interaction_count
    org.configuration_json = configuration_json
    org.auth_provider = auth_provider
    org.created_at = created_at  # type: ignore[reportAttributeAccessIssue]
    return org


def _make_org_row(**overrides) -> dict:
    defaults = {
        "id": 1,
        "created_at": 1700000000,
        "email": "test@example.com",
        "hashed_password": "hashed_pw",
        "is_active": True,
        "is_verified": False,
        "interaction_count": 0,
        "configuration_json": "",
        "auth_provider": "email",
    }
    defaults.update(overrides)
    return defaults


def _make_token_row(**overrides) -> dict:
    defaults = {
        "id": 1,
        "org_id": 1,
        "token": "rflx-abc123",
        "name": "Default",
        "created_at": 1700000000,
        "last_used_at": None,
    }
    defaults.update(overrides)
    return defaults


def _make_invitation_row(**overrides) -> dict:
    defaults = {
        "id": 1,
        "code": "INV-ABC",
        "is_used": False,
        "used_by_email": None,
        "used_at": None,
        "created_at": 1700000000,
        "expires_at": None,
    }
    defaults.update(overrides)
    return defaults


def _sb_response(rows: list[dict]) -> MagicMock:
    """Build a minimal Supabase APIResponse-like mock."""
    resp = MagicMock()
    resp.data = rows
    return resp


def _chain_mock(final_return: MagicMock | None = None) -> MagicMock:
    """Return a mock whose every attribute call returns itself (builder pattern),
    with `.execute()` returning *final_return*."""
    m = MagicMock()
    # Support fluent chaining: .select().eq().range().order() etc.
    m.select.return_value = m
    m.eq.return_value = m
    m.range.return_value = m
    m.order.return_value = m
    m.insert.return_value = m
    m.update.return_value = m
    m.delete.return_value = m
    m.or_.return_value = m
    m.with_for_update.return_value = m
    m.filter.return_value = m
    if final_return is not None:
        m.execute.return_value = final_return
    return m


# ===================================================================
# _supabase_row_to_organization
# ===================================================================
class TestSupabaseRowToOrganization:
    def test_full_row(self):
        from reflexio_ext.server.db.db_operations import (
            _supabase_row_to_organization,
        )

        row = _make_org_row()
        org = _supabase_row_to_organization(row)
        assert org.email == "test@example.com"
        assert org.id == 1
        assert org.is_active is True
        assert org.is_verified is False
        assert org.interaction_count == 0
        assert org.auth_provider == "email"

    def test_defaults_applied_when_keys_missing(self):
        from reflexio_ext.server.db.db_operations import (
            _supabase_row_to_organization,
        )

        row = {"id": 2, "email": "a@b.com"}
        org = _supabase_row_to_organization(row)
        assert org.is_active is True
        assert org.is_verified is False
        assert org.interaction_count == 0
        assert org.configuration_json == ""
        assert org.auth_provider == "email"

    def test_empty_row(self):
        from reflexio_ext.server.db.db_operations import (
            _supabase_row_to_organization,
        )

        org = _supabase_row_to_organization({})
        assert org.id is None
        assert org.email is None


# ===================================================================
# _row_to_invitation_code
# ===================================================================
class TestRowToInvitationCode:
    def test_full_row(self):
        from reflexio_ext.server.db.db_operations import _row_to_invitation_code

        row = _make_invitation_row(code="INV-123", is_used=True, used_by_email="u@e.com")
        inv = _row_to_invitation_code(row)
        assert inv.code == "INV-123"
        assert inv.is_used is True
        assert inv.used_by_email == "u@e.com"

    def test_defaults(self):
        from reflexio_ext.server.db.db_operations import _row_to_invitation_code

        inv = _row_to_invitation_code({})
        assert inv.is_used is False
        assert inv.used_by_email is None


# ===================================================================
# _row_to_api_token
# ===================================================================
class TestRowToApiToken:
    def test_full_row(self):
        from reflexio_ext.server.db.db_operations import _row_to_api_token

        row = _make_token_row(token="rflx-xyz", name="MyToken")
        token = _row_to_api_token(row)
        assert token.token == "rflx-xyz"
        assert token.name == "MyToken"
        assert token.last_used_at is None

    def test_defaults(self):
        from reflexio_ext.server.db.db_operations import _row_to_api_token

        token = _row_to_api_token({})
        assert token.name == "Default"


# ===================================================================
# get_organization_by_email
# ===================================================================
class TestGetOrganizationByEmail:
    # --- S3 mode ---
    @patch(_GET_S3)
    @patch(_IS_S3, return_value=True)
    def test_s3_mode(self, _is_s3, mock_get_s3):
        from reflexio_ext.server.db.db_operations import get_organization_by_email

        s3 = MagicMock()
        expected = _make_org()
        s3.get_organization_by_email.return_value = expected
        mock_get_s3.return_value = s3

        result = get_organization_by_email(MagicMock(), "test@example.com")
        assert result is expected
        s3.get_organization_by_email.assert_called_once_with("test@example.com")

    # --- Supabase mode, found ---
    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_found(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_organization_by_email

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([_make_org_row()]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        result = get_organization_by_email(MagicMock(), "test@example.com")
        assert result is not None
        assert result.email == "test@example.com"

    # --- Supabase mode, not found ---
    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_not_found(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_organization_by_email

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        result = get_organization_by_email(MagicMock(), "nobody@example.com")
        assert result is None

    # --- SQLAlchemy mode, found ---
    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_found(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_organization_by_email

        session = MagicMock()
        expected = _make_org()
        session.query.return_value.filter.return_value.first.return_value = expected

        result = get_organization_by_email(session, "test@example.com")
        assert result is expected

    # --- SQLAlchemy mode, not found ---
    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_not_found(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_organization_by_email

        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None

        result = get_organization_by_email(session, "nobody@example.com")
        assert result is None

    # --- Session is None, no supabase ---
    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session_no_supabase(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_organization_by_email

        result = get_organization_by_email(None, "test@example.com")  # type: ignore[arg-type]
        assert result is None


# ===================================================================
# get_organizations
# ===================================================================
class TestGetOrganizations:
    @patch(_GET_S3)
    @patch(_IS_S3, return_value=True)
    def test_s3_mode(self, _is_s3, mock_get_s3):
        from reflexio_ext.server.db.db_operations import get_organizations

        s3 = MagicMock()
        s3.get_organizations.return_value = [_make_org()]
        mock_get_s3.return_value = s3

        result = get_organizations(MagicMock(), skip=0, limit=10)
        assert len(result) == 1
        s3.get_organizations.assert_called_once_with(skip=0, limit=10)

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_mode(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_organizations

        client = MagicMock()
        table_chain = _chain_mock(
            _sb_response([_make_org_row(), _make_org_row(id=2, email="b@b.com")])
        )
        client.table.return_value = table_chain
        mock_sb.return_value = client

        result = get_organizations(MagicMock(), skip=0, limit=100)
        assert len(result) == 2

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_mode(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_organizations

        session = MagicMock()
        session.query.return_value.offset.return_value.limit.return_value.all.return_value = [
            _make_org()
        ]

        result = get_organizations(session, skip=5, limit=20)
        assert len(result) == 1

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session_returns_empty(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_organizations

        result = get_organizations(None, skip=0, limit=10)  # type: ignore[arg-type]
        assert result == []


# ===================================================================
# create_organization
# ===================================================================
class TestCreateOrganization:
    @patch(_GET_S3)
    @patch(_IS_S3, return_value=True)
    def test_s3_mode(self, _is_s3, mock_get_s3):
        from reflexio_ext.server.db.db_operations import create_organization

        s3 = MagicMock()
        org = _make_org()
        s3.create_organization.return_value = org
        mock_get_s3.return_value = s3

        result = create_organization(MagicMock(), org)
        assert result is org
        s3.create_organization.assert_called_once_with(org)

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_created(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_organization

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([_make_org_row()]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        org = _make_org()
        result = create_organization(MagicMock(), org)
        assert result.email == "test@example.com"

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_empty_response_raises(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_organization

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        with pytest.raises(Exception, match="Failed to create organization"):
            create_organization(MagicMock(), _make_org())

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_mode(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_organization

        session = MagicMock()
        org = _make_org()

        result = create_organization(session, org)
        session.add.assert_called_once_with(org)
        session.commit.assert_called_once()
        session.refresh.assert_called_once_with(org)
        assert result is org

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session_raises(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_organization

        with pytest.raises(Exception, match="No session available"):
            create_organization(None, _make_org())  # type: ignore[arg-type]

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_defaults_for_none_fields(self, mock_sb, _is_s3):
        """Verify default values are applied when org fields are None."""
        from reflexio_ext.server.db.db_operations import create_organization

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([_make_org_row()]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        org = db_models.Organization()
        org.email = "new@example.com"  # type: ignore[reportAttributeAccessIssue]
        org.hashed_password = "pw"  # type: ignore[reportAttributeAccessIssue]
        # is_active, is_verified, interaction_count, configuration_json, auth_provider are None

        create_organization(MagicMock(), org)

        # Verify the insert was called with defaults
        call_args = table_chain.insert.call_args[0][0]
        assert call_args["is_active"] is True
        assert call_args["is_verified"] is False
        assert call_args["interaction_count"] == 0
        assert call_args["configuration_json"] == ""
        assert call_args["auth_provider"] == "email"


# ===================================================================
# update_organization
# ===================================================================
class TestUpdateOrganization:
    @patch(_GET_S3)
    @patch(_IS_S3, return_value=True)
    def test_s3_mode(self, _is_s3, mock_get_s3):
        from reflexio_ext.server.db.db_operations import update_organization

        s3 = MagicMock()
        org = _make_org()
        s3.update_organization.return_value = org
        mock_get_s3.return_value = s3

        result = update_organization(MagicMock(), org)
        assert result is org

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_updated(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import update_organization

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([_make_org_row(is_verified=True)]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        org = _make_org()
        result = update_organization(MagicMock(), org)
        assert result.is_verified is True

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_empty_response_raises(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import update_organization

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        with pytest.raises(Exception, match="Failed to update organization"):
            update_organization(MagicMock(), _make_org())

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_mode(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import update_organization

        session = MagicMock()
        org = _make_org()
        result = update_organization(session, org)
        session.commit.assert_called_once()
        session.refresh.assert_called_once_with(org)
        assert result is org

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session_raises(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import update_organization

        with pytest.raises(Exception, match="No session available"):
            update_organization(None, _make_org())  # type: ignore[arg-type]


# ===================================================================
# get_db_session
# ===================================================================
class TestGetDbSession:
    @patch(f"{_MOD}.SessionLocal", None)
    def test_supabase_mode_yields_none(self):
        from reflexio_ext.server.db.db_operations import get_db_session

        gen = get_db_session()
        val = next(gen)
        assert val is None

    @patch(f"{_MOD}.SessionLocal")
    def test_sqlite_mode_yields_session(self, mock_session_local):
        from reflexio_ext.server.db.db_operations import get_db_session

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        gen = get_db_session()
        val = next(gen)
        assert val is mock_db

        # Exhaust the generator to trigger finally block
        with pytest.raises(StopIteration):
            next(gen)
        mock_db.close.assert_called_once()

    @patch(f"{_MOD}.SessionLocal")
    def test_sqlite_session_closes_on_exception(self, mock_session_local):
        from reflexio_ext.server.db.db_operations import get_db_session

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        gen = get_db_session()
        next(gen)
        # Simulate an exception thrown into the generator
        with pytest.raises(RuntimeError):
            gen.throw(RuntimeError("boom"))
        mock_db.close.assert_called_once()


# ===================================================================
# get_invitation_code
# ===================================================================
class TestGetInvitationCode:
    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_found(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_invitation_code

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([_make_invitation_row(code="INV-X")]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        result = get_invitation_code(MagicMock(), "INV-X")
        assert result is not None
        assert result.code == "INV-X"

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_not_found(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_invitation_code

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        result = get_invitation_code(MagicMock(), "NOPE")
        assert result is None

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_found(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_invitation_code

        session = MagicMock()
        inv = db_models.InvitationCode()
        inv.code = "INV-Y"  # type: ignore[reportAttributeAccessIssue]
        session.query.return_value.filter.return_value.first.return_value = inv

        result = get_invitation_code(session, "INV-Y")
        assert result is inv

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_invitation_code

        result = get_invitation_code(None, "CODE")  # type: ignore[arg-type]
        assert result is None


# ===================================================================
# claim_invitation_code
# ===================================================================
class TestClaimInvitationCode:
    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_claimed(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import claim_invitation_code

        client = MagicMock()
        claimed_row = _make_invitation_row(is_used=True, used_by_email="user@e.com")
        table_chain = _chain_mock(_sb_response([claimed_row]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        result = claim_invitation_code(MagicMock(), "INV-1", "user@e.com")
        assert result is not None
        assert result.is_used is True
        assert result.used_by_email == "user@e.com"

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_not_found_or_already_used(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import claim_invitation_code

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        result = claim_invitation_code(MagicMock(), "BAD", "user@e.com")
        assert result is None

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_claimed_successfully(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import claim_invitation_code

        session = MagicMock()
        inv = MagicMock()
        inv.is_used = False
        inv.expires_at = None
        session.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
            inv
        )

        result = claim_invitation_code(session, "INV-1", "user@e.com")
        assert result is inv
        assert inv.is_used is True
        assert inv.used_by_email == "user@e.com"
        session.flush.assert_called_once()

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_code_not_found(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import claim_invitation_code

        session = MagicMock()
        session.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
            None
        )

        result = claim_invitation_code(session, "NOPE", "user@e.com")
        assert result is None

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_code_already_used(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import claim_invitation_code

        session = MagicMock()
        inv = MagicMock()
        inv.is_used = True
        session.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
            inv
        )

        result = claim_invitation_code(session, "USED", "user@e.com")
        assert result is None

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_code_expired(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import claim_invitation_code

        session = MagicMock()
        inv = MagicMock()
        inv.is_used = False
        inv.expires_at = 1  # Very old timestamp = expired
        session.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
            inv
        )

        result = claim_invitation_code(session, "EXPIRED", "user@e.com")
        assert result is None

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_code_not_expired(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import claim_invitation_code

        session = MagicMock()
        inv = MagicMock()
        inv.is_used = False
        inv.expires_at = 99999999999  # Far future
        session.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
            inv
        )

        result = claim_invitation_code(session, "VALID", "user@e.com")
        assert result is inv

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import claim_invitation_code

        result = claim_invitation_code(None, "CODE", "e@e.com")  # type: ignore[arg-type]
        assert result is None


# ===================================================================
# release_invitation_code
# ===================================================================
class TestReleaseInvitationCode:
    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_mode(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import release_invitation_code

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        release_invitation_code(MagicMock(), "INV-1")
        # Verify update was called with reset values
        table_chain.update.assert_called_once_with(
            {"is_used": False, "used_by_email": None, "used_at": None}
        )

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_found(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import release_invitation_code

        session = MagicMock()
        inv = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = inv

        release_invitation_code(session, "INV-1")
        assert inv.is_used is False
        assert inv.used_by_email is None
        assert inv.used_at is None
        session.flush.assert_called_once()

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_not_found(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import release_invitation_code

        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None

        # Should not raise, just no-op
        release_invitation_code(session, "NOPE")
        session.flush.assert_not_called()

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import release_invitation_code

        # Should not raise
        release_invitation_code(None, "INV-1")  # type: ignore[arg-type]


# ===================================================================
# create_invitation_code
# ===================================================================
class TestCreateInvitationCode:
    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_created(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_invitation_code

        client = MagicMock()
        table_chain = _chain_mock(
            _sb_response([_make_invitation_row(code="NEW-CODE")])
        )
        client.table.return_value = table_chain
        mock_sb.return_value = client

        result = create_invitation_code(MagicMock(), "NEW-CODE")
        assert result.code == "NEW-CODE"

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_with_expiry(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_invitation_code

        client = MagicMock()
        table_chain = _chain_mock(
            _sb_response([_make_invitation_row(code="EXP", expires_at=9999999999)])
        )
        client.table.return_value = table_chain
        mock_sb.return_value = client

        result = create_invitation_code(MagicMock(), "EXP", expires_at=9999999999)
        assert result.code == "EXP"
        # Verify expires_at was passed in the insert data
        insert_data = table_chain.insert.call_args[0][0]
        assert insert_data["expires_at"] == 9999999999

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_empty_response_raises(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_invitation_code

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        with pytest.raises(Exception, match="Failed to create invitation code"):
            create_invitation_code(MagicMock(), "FAIL")

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_mode(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_invitation_code

        session = MagicMock()
        result = create_invitation_code(session, "NEW-CODE", expires_at=9999)
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert result.code == "NEW-CODE"
        assert result.expires_at == 9999

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session_raises(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_invitation_code

        with pytest.raises(Exception, match="No session available"):
            create_invitation_code(None, "FAIL")  # type: ignore[arg-type]


# ===================================================================
# create_api_token
# ===================================================================
class TestCreateApiToken:
    @patch(_GET_S3)
    @patch(_IS_S3, return_value=True)
    def test_s3_mode(self, _is_s3, mock_get_s3):
        from reflexio_ext.server.db.db_operations import create_api_token

        s3 = MagicMock()
        expected = db_models.ApiToken()
        s3.create_api_token.return_value = expected
        mock_get_s3.return_value = s3

        result = create_api_token(MagicMock(), 1, "rflx-test", "MyToken")
        assert result is expected
        s3.create_api_token.assert_called_once_with(1, "rflx-test", "MyToken")

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_created(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_api_token

        client = MagicMock()
        table_chain = _chain_mock(
            _sb_response([_make_token_row(token="rflx-new")])
        )
        client.table.return_value = table_chain
        mock_sb.return_value = client

        result = create_api_token(MagicMock(), 1, "rflx-new")
        assert result.token == "rflx-new"

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_empty_response_raises(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_api_token

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        with pytest.raises(Exception, match="Failed to create API token"):
            create_api_token(MagicMock(), 1, "rflx-fail")

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_mode(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_api_token

        session = MagicMock()
        result = create_api_token(session, 1, "rflx-tok", "Dev")
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert result.token == "rflx-tok"
        assert result.name == "Dev"
        assert result.org_id == 1

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session_raises(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import create_api_token

        with pytest.raises(Exception, match="No session available"):
            create_api_token(None, 1, "rflx-x")  # type: ignore[arg-type]


# ===================================================================
# get_api_tokens_by_org_id
# ===================================================================
class TestGetApiTokensByOrgId:
    @patch(_GET_S3)
    @patch(_IS_S3, return_value=True)
    def test_s3_mode(self, _is_s3, mock_get_s3):
        from reflexio_ext.server.db.db_operations import get_api_tokens_by_org_id

        s3 = MagicMock()
        s3.get_api_tokens_by_org_id.return_value = [db_models.ApiToken()]
        mock_get_s3.return_value = s3

        result = get_api_tokens_by_org_id(MagicMock(), 1)
        assert len(result) == 1

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_mode(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_api_tokens_by_org_id

        client = MagicMock()
        table_chain = _chain_mock(
            _sb_response([_make_token_row(), _make_token_row(id=2, token="rflx-2")])
        )
        client.table.return_value = table_chain
        mock_sb.return_value = client

        result = get_api_tokens_by_org_id(MagicMock(), 1)
        assert len(result) == 2

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_mode(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_api_tokens_by_org_id

        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            db_models.ApiToken()
        ]

        result = get_api_tokens_by_org_id(session, 1)
        assert len(result) == 1

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session_returns_empty(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_api_tokens_by_org_id

        result = get_api_tokens_by_org_id(None, 1)  # type: ignore[arg-type]
        assert result == []


# ===================================================================
# get_org_by_api_token
# ===================================================================
class TestGetOrgByApiToken:
    @patch(_GET_S3)
    @patch(_IS_S3, return_value=True)
    def test_s3_mode(self, _is_s3, mock_get_s3):
        from reflexio_ext.server.db.db_operations import get_org_by_api_token

        s3 = MagicMock()
        expected = _make_org()
        s3.get_org_by_api_token.return_value = expected
        mock_get_s3.return_value = s3

        result = get_org_by_api_token(MagicMock(), "rflx-test")
        assert result is expected

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_found(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_org_by_api_token

        client = MagicMock()

        # First call: api_tokens table lookup returns org_id
        token_chain = _chain_mock(_sb_response([{"org_id": 5}]))
        # Second call: organizations table lookup returns org row
        org_chain = _chain_mock(_sb_response([_make_org_row(id=5)]))

        client.table.side_effect = [token_chain, org_chain]
        mock_sb.return_value = client

        result = get_org_by_api_token(MagicMock(), "rflx-test")
        assert result is not None
        assert result.id == 5

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_token_not_found(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_org_by_api_token

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        result = get_org_by_api_token(MagicMock(), "rflx-nope")
        assert result is None

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_org_not_found(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_org_by_api_token

        client = MagicMock()
        token_chain = _chain_mock(_sb_response([{"org_id": 999}]))
        org_chain = _chain_mock(_sb_response([]))
        client.table.side_effect = [token_chain, org_chain]
        mock_sb.return_value = client

        result = get_org_by_api_token(MagicMock(), "rflx-orphan")
        assert result is None

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_found(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_org_by_api_token

        session = MagicMock()
        api_token = MagicMock()
        api_token.org_id = 3
        org = _make_org(id_=3)

        # First query: api_tokens
        # Second query: organizations
        session.query.return_value.filter.return_value.first.side_effect = [
            api_token,
            org,
        ]

        result = get_org_by_api_token(session, "rflx-test")
        assert result is org

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_token_not_found(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_org_by_api_token

        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None

        result = get_org_by_api_token(session, "rflx-nope")
        assert result is None

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import get_org_by_api_token

        result = get_org_by_api_token(None, "rflx-x")  # type: ignore[arg-type]
        assert result is None


# ===================================================================
# delete_api_token
# ===================================================================
class TestDeleteApiToken:
    @patch(_GET_S3)
    @patch(_IS_S3, return_value=True)
    def test_s3_mode(self, _is_s3, mock_get_s3):
        from reflexio_ext.server.db.db_operations import delete_api_token

        s3 = MagicMock()
        s3.delete_api_token.return_value = True
        mock_get_s3.return_value = s3

        assert delete_api_token(MagicMock(), 1, 1) is True
        s3.delete_api_token.assert_called_once_with(1, 1)

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_deleted(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_api_token

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([_make_token_row()]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        assert delete_api_token(MagicMock(), 1, 1) is True

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_not_found(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_api_token

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        assert delete_api_token(MagicMock(), 99, 1) is False

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_deleted(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_api_token

        session = MagicMock()
        token_obj = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = token_obj

        assert delete_api_token(session, 1, 1) is True
        session.delete.assert_called_once_with(token_obj)
        session.commit.assert_called_once()

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_not_found(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_api_token

        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None

        assert delete_api_token(session, 99, 1) is False

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_api_token

        assert delete_api_token(None, 1, 1) is False  # type: ignore[arg-type]


# ===================================================================
# delete_all_api_tokens_for_org
# ===================================================================
class TestDeleteAllApiTokensForOrg:
    @patch(_GET_S3)
    @patch(_IS_S3, return_value=True)
    def test_s3_mode(self, _is_s3, mock_get_s3):
        from reflexio_ext.server.db.db_operations import delete_all_api_tokens_for_org

        s3 = MagicMock()
        s3.delete_all_api_tokens_for_org.return_value = 3
        mock_get_s3.return_value = s3

        assert delete_all_api_tokens_for_org(MagicMock(), 1) == 3

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_mode(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_all_api_tokens_for_org

        client = MagicMock()
        table_chain = _chain_mock(
            _sb_response([_make_token_row(), _make_token_row(id=2)])
        )
        client.table.return_value = table_chain
        mock_sb.return_value = client

        assert delete_all_api_tokens_for_org(MagicMock(), 1) == 2

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_mode(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_all_api_tokens_for_org

        session = MagicMock()
        session.query.return_value.filter.return_value.delete.return_value = 5

        assert delete_all_api_tokens_for_org(session, 1) == 5
        session.commit.assert_called_once()

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_all_api_tokens_for_org

        assert delete_all_api_tokens_for_org(None, 1) == 0  # type: ignore[arg-type]


# ===================================================================
# delete_organization
# ===================================================================
class TestDeleteOrganization:
    @patch(_GET_S3)
    @patch(_IS_S3, return_value=True)
    def test_s3_mode(self, _is_s3, mock_get_s3):
        from reflexio_ext.server.db.db_operations import delete_organization

        s3 = MagicMock()
        s3.delete_organization.return_value = True
        mock_get_s3.return_value = s3

        assert delete_organization(MagicMock(), 1) is True

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_deleted(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_organization

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([_make_org_row()]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        assert delete_organization(MagicMock(), 1) is True

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB)
    def test_supabase_not_found(self, mock_sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_organization

        client = MagicMock()
        table_chain = _chain_mock(_sb_response([]))
        client.table.return_value = table_chain
        mock_sb.return_value = client

        assert delete_organization(MagicMock(), 99) is False

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_deleted(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_organization

        session = MagicMock()
        org_obj = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = org_obj

        assert delete_organization(session, 1) is True
        session.delete.assert_called_once_with(org_obj)
        session.commit.assert_called_once()

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_sqlite_not_found(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_organization

        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None

        assert delete_organization(session, 99) is False

    @patch(_IS_S3, return_value=False)
    @patch(_GET_SB, return_value=None)
    def test_no_session(self, _sb, _is_s3):
        from reflexio_ext.server.db.db_operations import delete_organization

        assert delete_organization(None, 1) is False  # type: ignore[arg-type]


# ===================================================================
# add_db_model
# ===================================================================
class TestAddDbModel:
    def test_success(self):
        from reflexio_ext.server.db.db_operations import add_db_model

        session = MagicMock()
        model = MagicMock()
        result = add_db_model(session, model)
        session.add.assert_called_once_with(model)
        session.commit.assert_called_once()
        session.refresh.assert_called_once_with(model)
        assert result is model

    def test_no_session_raises(self):
        from reflexio_ext.server.db.db_operations import add_db_model

        with pytest.raises(Exception, match="Cannot add model"):
            add_db_model(None, MagicMock())  # type: ignore[arg-type]


# ===================================================================
# db_session_context
# ===================================================================
class TestDbSessionContext:
    @patch(f"{_MOD}.SessionLocal", None)
    def test_supabase_mode_yields_none(self):
        from reflexio_ext.server.db.db_operations import db_session_context

        with db_session_context() as s:
            assert s is None

    @patch(f"{_MOD}.SessionLocal")
    def test_sqlite_mode(self, mock_session_local):
        from reflexio_ext.server.db.db_operations import db_session_context

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        with db_session_context() as s:
            assert s is mock_db
        mock_db.close.assert_called_once()

    @patch(f"{_MOD}.SessionLocal")
    def test_sqlite_closes_on_exception(self, mock_session_local):
        from reflexio_ext.server.db.db_operations import db_session_context

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        with pytest.raises(ValueError):
            with db_session_context() as _s:
                raise ValueError("boom")
        mock_db.close.assert_called_once()


# ===================================================================
# _rows helper
# ===================================================================
class TestRowsHelper:
    def test_casts_data(self):
        from reflexio_ext.server.db.db_operations import _rows

        resp = MagicMock()
        resp.data = [{"a": 1}, {"b": 2}]
        result = _rows(resp)
        assert result == [{"a": 1}, {"b": 2}]

    def test_empty_data(self):
        from reflexio_ext.server.db.db_operations import _rows

        resp = MagicMock()
        resp.data = []
        assert _rows(resp) == []


# ===================================================================
# _is_self_host_s3_mode
# ===================================================================
class TestIsSelfHostS3Mode:
    @patch(f"{_MOD}.is_s3_org_storage_ready", return_value=True)
    @patch(f"{_MOD}.SELF_HOST_MODE", True)
    def test_both_true(self, _ready):
        from reflexio_ext.server.db.db_operations import _is_self_host_s3_mode

        assert _is_self_host_s3_mode() is True

    @patch(f"{_MOD}.is_s3_org_storage_ready", return_value=False)
    @patch(f"{_MOD}.SELF_HOST_MODE", True)
    def test_self_host_but_s3_not_ready(self, _ready):
        from reflexio_ext.server.db.db_operations import _is_self_host_s3_mode

        assert _is_self_host_s3_mode() is False

    @patch(f"{_MOD}.is_s3_org_storage_ready", return_value=True)
    @patch(f"{_MOD}.SELF_HOST_MODE", False)
    def test_not_self_host(self, _ready):
        from reflexio_ext.server.db.db_operations import _is_self_host_s3_mode

        assert _is_self_host_s3_mode() is False
