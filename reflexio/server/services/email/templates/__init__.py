"""
Email templates module.

Each email type has its own file with HTML and text template functions.
"""

from reflexio.server.services.email.templates.password_reset import (
    get_password_reset_email_html,
    get_password_reset_email_text,
)
from reflexio.server.services.email.templates.verification import (
    get_verification_email_html,
    get_verification_email_text,
)

__all__ = [
    "get_verification_email_html",
    "get_verification_email_text",
    "get_password_reset_email_html",
    "get_password_reset_email_text",
]
