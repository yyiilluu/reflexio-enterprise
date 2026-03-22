"""Tests for EmailService (AWS SES email sending)."""

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from reflexio_ext.server.services.email.email_service import (
    EmailService,
    _get_aws_region,
    _get_frontend_url,
    _get_ses_sender_email,
    get_email_service,
)


# ---------------------------------------------------------------------------
# Helper env functions
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    def test_get_aws_region_default(self, monkeypatch):
        monkeypatch.delenv("AWS_REGION", raising=False)
        assert _get_aws_region() == "us-east-1"

    def test_get_aws_region_custom(self, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        assert _get_aws_region() == "eu-west-1"

    def test_get_ses_sender_email_default(self, monkeypatch):
        monkeypatch.delenv("SES_SENDER_EMAIL", raising=False)
        assert _get_ses_sender_email() == "noreply@reflexio.com"

    def test_get_ses_sender_email_custom(self, monkeypatch):
        monkeypatch.setenv("SES_SENDER_EMAIL", "custom@example.com")
        assert _get_ses_sender_email() == "custom@example.com"

    def test_get_frontend_url_default(self, monkeypatch):
        monkeypatch.delenv("FRONTEND_URL", raising=False)
        assert _get_frontend_url() == "http://localhost:8080"

    def test_get_frontend_url_custom(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_URL", "https://app.example.com")
        assert _get_frontend_url() == "https://app.example.com"


# ---------------------------------------------------------------------------
# EmailService
# ---------------------------------------------------------------------------

class TestEmailService:
    def _make_service(self):
        svc = EmailService()
        mock_client = MagicMock()
        svc._client = mock_client
        return svc, mock_client

    def test_lazy_client_creation(self):
        with patch(
            "reflexio_ext.server.services.email.email_service.boto3"
        ) as mock_boto:
            mock_boto.client.return_value = MagicMock()
            svc = EmailService()
            assert svc._client is None
            _ = svc.client
            mock_boto.client.assert_called_once_with("ses", region_name=_get_aws_region())
            assert svc._client is not None

    def test_client_reuse(self):
        svc = EmailService()
        svc._client = MagicMock()
        first = svc.client
        second = svc.client
        assert first is second

    @patch(
        "reflexio_ext.server.services.email.email_service._get_frontend_url",
        return_value="https://app.test",
    )
    @patch(
        "reflexio_ext.server.services.email.email_service.get_verification_email_html",
        return_value="<html>verify</html>",
    )
    @patch(
        "reflexio_ext.server.services.email.email_service.get_verification_email_text",
        return_value="verify text",
    )
    def test_send_verification_email_success(
        self, mock_text, mock_html, mock_url
    ):
        svc, mock_client = self._make_service()
        mock_client.send_email.return_value = {"MessageId": "msg-123"}

        result = svc.send_verification_email("user@test.com", "token-abc")
        assert result is True
        mock_client.send_email.assert_called_once()
        # Verify the link construction
        mock_html.assert_called_once_with(
            "https://app.test/verify-email?token=token-abc"
        )

    @patch(
        "reflexio_ext.server.services.email.email_service._get_frontend_url",
        return_value="https://app.test",
    )
    @patch(
        "reflexio_ext.server.services.email.email_service.get_password_reset_email_html",
        return_value="<html>reset</html>",
    )
    @patch(
        "reflexio_ext.server.services.email.email_service.get_password_reset_email_text",
        return_value="reset text",
    )
    def test_send_password_reset_email_success(
        self, mock_text, mock_html, mock_url
    ):
        svc, mock_client = self._make_service()
        mock_client.send_email.return_value = {"MessageId": "msg-456"}

        result = svc.send_password_reset_email("user@test.com", "reset-tok")
        assert result is True
        mock_html.assert_called_once_with(
            "https://app.test/reset-password?token=reset-tok"
        )

    def test_send_email_ses_client_error(self):
        svc, mock_client = self._make_service()
        mock_client.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "bad"}},
            "SendEmail",
        )
        result = svc._send_email(
            "user@test.com", "Subject", "<html/>", "text"
        )
        assert result is False

    def test_send_email_success(self):
        svc, mock_client = self._make_service()
        mock_client.send_email.return_value = {"MessageId": "msg-789"}
        result = svc._send_email(
            "user@test.com", "Hello", "<html/>", "text"
        )
        assert result is True


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestGetEmailService:
    def test_returns_email_service_instance(self):
        # Reset singleton
        import reflexio_ext.server.services.email.email_service as mod
        mod._email_service = None

        svc = get_email_service()
        assert isinstance(svc, EmailService)

    def test_returns_same_instance(self):
        import reflexio_ext.server.services.email.email_service as mod
        mod._email_service = None

        first = get_email_service()
        second = get_email_service()
        assert first is second
