"""
Password reset email template.

Sent when a user requests to reset their password.
"""

from reflexio_ext.server.services.email.templates.base import (
    BG_CARD,
    BG_PRIMARY,
    BRAND_PRIMARY,
    BRAND_SECONDARY,
    COMPANY_NAME,
    TEXT_MUTED,
    TEXT_SECONDARY,
    get_email_footer,
    get_email_header,
    get_email_wrapper_end,
    get_email_wrapper_start,
    get_text_footer,
)


def get_password_reset_email_html(reset_link: str) -> str:
    """
    Generate modern, responsive HTML email template for password reset.

    Args:
        reset_link (str): The password reset URL

    Returns:
        str: HTML email content
    """
    wrapper_start = get_email_wrapper_start()
    header = get_email_header()
    footer = get_email_footer()
    wrapper_end = get_email_wrapper_end()

    content = f"""<!-- Content -->
<tr>
    <td style="padding: 48px 40px;">
        <h2 style="margin: 0 0 16px; font-size: 26px; font-weight: 600; color: {BRAND_PRIMARY}; text-align: center; letter-spacing: -0.3px;">Reset Your Password</h2>
        <p style="margin: 0 0 32px; font-size: 16px; line-height: 1.7; color: {TEXT_SECONDARY}; text-align: center;">
            We received a request to reset your password for your {COMPANY_NAME} account. Click the button below to create a new password.
        </p>
        <!-- CTA Button -->
        <table role="presentation" cellspacing="0" cellpadding="0" style="margin: 0 auto 32px;">
            <tr>
                <td style="border-radius: 10px; background: linear-gradient(135deg, {BRAND_SECONDARY} 0%, {BRAND_PRIMARY} 100%); box-shadow: 0 4px 14px rgba(69, 123, 157, 0.4);">
                    <a href="{reset_link}" target="_blank" style="display: inline-block; padding: 18px 40px; font-size: 16px; font-weight: 600; color: #ffffff; text-decoration: none; letter-spacing: 0.3px;">
                        Reset Password
                    </a>
                </td>
            </tr>
        </table>
        <!-- Expiration notice -->
        <div style="text-align: center; margin-bottom: 32px;">
            <span style="display: inline-block; padding: 8px 16px; background-color: #fef3c7; border-radius: 20px; font-size: 13px; color: #92400e; font-weight: 500;">
                This link expires in 1 hour
            </span>
        </div>
        <p style="margin: 0; font-size: 14px; color: {TEXT_MUTED}; text-align: center;">
            If you didn't request a password reset, you can safely ignore this email. Your password will not be changed.
        </p>
        <!-- Fallback Link -->
        <div style="margin-top: 40px; padding: 20px; background-color: {BG_PRIMARY}; border-radius: 10px; border: 1px solid #e2e8f0;">
            <p style="margin: 0 0 10px; font-size: 12px; color: {TEXT_SECONDARY}; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px;">
                Button not working? Copy this link:
            </p>
            <p style="margin: 0; font-size: 13px; word-break: break-all; color: {BRAND_SECONDARY}; font-family: 'Courier New', monospace; background-color: {BG_CARD}; padding: 12px; border-radius: 6px; border: 1px solid #e2e8f0;">
                {reset_link}
            </p>
        </div>
    </td>
</tr>"""

    return f"{wrapper_start}\n{header}\n{content}\n{footer}\n{wrapper_end}"


def get_password_reset_email_text(reset_link: str) -> str:
    """
    Generate plain text email for password reset.

    Args:
        reset_link (str): The password reset URL

    Returns:
        str: Plain text email content
    """
    text_footer = get_text_footer()

    return f"""Reset Your Password

We received a request to reset your password for your {COMPANY_NAME} account.

Click the link below to create a new password:

{reset_link}

This link will expire in 1 hour.

If you didn't request a password reset, you can safely ignore this email. Your password will not be changed.

{text_footer}"""
