"""
Base email template components shared across all email types.

Contains brand colors, header, footer, and common styles.
"""

# Brand colors
BRAND_PRIMARY = "#1d3557"
BRAND_SECONDARY = "#457b9d"
BRAND_LIGHT = "#a8dadc"
TEXT_PRIMARY = "#1d3557"
TEXT_SECONDARY = "#64748b"
TEXT_MUTED = "#94a3b8"
BG_PRIMARY = "#f8fafc"
BG_CARD = "#ffffff"

# Company info
COMPANY_NAME = "Reflexio"
COMPANY_TAGLINE = "Memory That Makes Agents Personal and Self Improve"
SUPPORT_EMAIL = "support@reflexio.com"
COPYRIGHT_YEAR = "2024"


def get_email_header() -> str:
    """
    Generate the email header with branding.

    Returns:
        str: HTML header section
    """
    return f"""<!-- Header with gradient -->
<tr>
    <td style="padding: 48px 40px 32px; text-align: center; background: linear-gradient(135deg, {BRAND_PRIMARY} 0%, {BRAND_SECONDARY} 100%);">
        <h1 style="margin: 0; font-size: 32px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px;">{COMPANY_NAME}</h1>
        <p style="margin: 12px 0 0; font-size: 15px; color: rgba(255, 255, 255, 0.85); font-weight: 400;">{COMPANY_TAGLINE}</p>
    </td>
</tr>"""


def get_email_footer() -> str:
    """
    Generate the email footer with support info and copyright.

    Returns:
        str: HTML footer section
    """
    return f"""<!-- Footer -->
<tr>
    <td style="padding: 24px 40px 32px; background-color: {BG_PRIMARY}; border-top: 1px solid #e2e8f0;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
            <tr>
                <td style="text-align: center;">
                    <p style="margin: 0 0 8px; font-size: 13px; color: {TEXT_SECONDARY};">
                        Need help? Contact us at <a href="mailto:{SUPPORT_EMAIL}" style="color: {BRAND_SECONDARY}; text-decoration: none;">{SUPPORT_EMAIL}</a>
                    </p>
                    <p style="margin: 0; font-size: 12px; color: {TEXT_MUTED};">
                        &copy; {COPYRIGHT_YEAR} {COMPANY_NAME}. All rights reserved.
                    </p>
                </td>
            </tr>
        </table>
    </td>
</tr>"""


def get_email_wrapper_start() -> str:
    """
    Generate the opening HTML wrapper for emails.

    Returns:
        str: HTML document start and outer wrapper
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{COMPANY_NAME}</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: {BG_PRIMARY};">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="min-height: 100vh;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 600px; background-color: {BG_CARD}; border-radius: 16px; box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08); overflow: hidden;">"""


def get_email_wrapper_end() -> str:
    """
    Generate the closing HTML wrapper for emails.

    Returns:
        str: HTML document end and outer wrapper close
    """
    return f"""                </table>
                <!-- Additional footer text -->
                <p style="margin-top: 24px; font-size: 12px; color: {TEXT_MUTED}; text-align: center;">
                    This is an automated message from {COMPANY_NAME}. Please do not reply to this email.
                </p>
            </td>
        </tr>
    </table>
</body>
</html>"""


def get_text_footer() -> str:
    """
    Generate plain text footer for emails.

    Returns:
        str: Plain text footer
    """
    return f"""Need help? Contact us at {SUPPORT_EMAIL}

Best regards,
The {COMPANY_NAME} Team

---
This is an automated message from {COMPANY_NAME}. Please do not reply to this email."""
