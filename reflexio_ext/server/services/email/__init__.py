"""
Email service module for sending verification and notification emails.
"""

from reflexio_ext.server.services.email.email_service import (
    EmailService,
    get_email_service,
)

__all__ = ["EmailService", "get_email_service"]
