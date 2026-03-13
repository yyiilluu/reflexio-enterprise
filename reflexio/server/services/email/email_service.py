"""
Email service for sending verification and notification emails via AWS SES.
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError

from reflexio.server.services.email.templates import (
    get_password_reset_email_html,
    get_password_reset_email_text,
    get_verification_email_html,
    get_verification_email_text,
)

logger = logging.getLogger(__name__)


def _get_aws_region() -> str:
    """Get AWS region from environment at runtime."""
    return os.getenv("AWS_REGION", "us-east-1")


def _get_ses_sender_email() -> str:
    """Get SES sender email from environment at runtime."""
    return os.getenv("SES_SENDER_EMAIL", "noreply@reflexio.com")


def _get_frontend_url() -> str:
    """Get frontend URL from environment at runtime."""
    return os.getenv("FRONTEND_URL", "http://localhost:8080")


class EmailService:
    """
    Service for sending emails via AWS SES.
    """

    def __init__(self):
        """
        Initialize the SES client.
        """
        self._client: boto3.client | None = None  # type: ignore[reportGeneralTypeIssues]

    @property
    def client(self) -> boto3.client:  # type: ignore[reportGeneralTypeIssues]
        """
        Lazy-load the SES client.

        Returns:
            boto3.client: The SES client instance
        """
        if self._client is None:
            self._client = boto3.client("ses", region_name=_get_aws_region())
        return self._client

    def send_verification_email(self, to_email: str, verification_token: str) -> bool:
        """
        Send a verification email to the user.

        Args:
            to_email (str): Recipient email address
            verification_token (str): JWT verification token

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        verification_link = (
            f"{_get_frontend_url()}/verify-email?token={verification_token}"
        )

        subject = "Verify your Reflexio account"
        html_body = get_verification_email_html(verification_link)
        text_body = get_verification_email_text(verification_link)

        return self._send_email(to_email, subject, html_body, text_body)

    def send_password_reset_email(self, to_email: str, reset_token: str) -> bool:
        """
        Send a password reset email to the user.

        Args:
            to_email (str): Recipient email address
            reset_token (str): JWT password reset token

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        reset_link = f"{_get_frontend_url()}/reset-password?token={reset_token}"

        subject = "Reset your Reflexio password"
        html_body = get_password_reset_email_html(reset_link)
        text_body = get_password_reset_email_text(reset_link)

        return self._send_email(to_email, subject, html_body, text_body)

    def _send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> bool:
        """
        Send an email via AWS SES.

        Args:
            to_email (str): Recipient email address
            subject (str): Email subject
            html_body (str): HTML email body
            text_body (str): Plain text email body

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            response = self.client.send_email(
                Source=_get_ses_sender_email(),
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                    },
                },
            )
            logger.info(
                "Verification email sent to %s, MessageId: %s",
                to_email,
                response["MessageId"],
            )
            return True
        except ClientError as e:
            logger.error("Failed to send email to %s: %s", to_email, e)
            return False


# Singleton instance
_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    """
    Get the singleton email service instance.

    Returns:
        EmailService: The email service instance
    """
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
