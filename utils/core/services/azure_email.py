from __future__ import annotations
import logging
from datetime import datetime
from typing import Any
from azure.communication.email.aio import EmailClient
from azure.core.credentials import AzureKeyCredential
from constants.config import settings

logger = logging.getLogger(__name__)

class AzureEmailManager:
    """
    Manager for sending automated emails using Azure Communication Services.
    """
    def __init__(self):
        self._connection_string = settings.AZURE_COMMUNICATION_CONNECTION_STRING
        self._sender_address = settings.AZURE_SENDER_EMAIL
        self._endpoint = getattr(settings, "AZURE_EMAIL_ENDPOINT", None)
        self._key = getattr(settings, "AZURE_EMAIL_KEY", None)


    def _get_template(self, name: str, **kwargs) -> str:
        """Professional HTML email templates for candidate communication."""
        candidate_name = kwargs.get("candidate_name", "Candidate")
        job_title = kwargs.get("job_title", "the position")
        
        # Base Styles
        base_style = """
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #1a1a1a;
            line-height: 1.6;
            margin: 0;
            padding: 0;
            background-color: #f9fafb;
        """
        container_style = """
            max-width: 600px;
            margin: 20px auto;
            background: #ffffff;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            border: 1px solid #e5e7eb;
        """
        header_style = "padding: 32px 40px 20px; text-align: left;"
        body_style = "padding: 0 40px 32px;"
        footer_style = """
            padding: 24px 40px;
            background: #f3f4f6;
            color: #6b7280;
            font-size: 13px;
            border-top: 1px solid #e5e7eb;
        """
        button_style = """
            display: inline-block;
            background: #111827;
            color: #ffffff;
            padding: 14px 28px;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 16px;
            margin: 24px 0;
        """

        # Content blocks based on template name
        if name == "invite":
            url = f"{settings.FRONTEND_BASE_URL}/interview.html?token={kwargs.get('session_token')}"
            title = "Interview Invitation"
            content = f"""
                <p>Dear {candidate_name},</p>
                <p>Thank you for your interest in the <strong>{job_title}</strong> position at our company. We've reviewed your application and would like to invite you to an interview.</p>
                <p>This conversational session is designed to learn more about your skills and experience in a flexible, interactive format. You can start the interview at your convenience by clicking the button below:</p>
                <div style="text-align: center;">
                    <a href="{url}" style="{button_style}">Start Voice Interview</a>
                </div>
                <p>The link is valid for {settings.INTERVIEW_LINK_EXPIRY_HOURS} hours. Please ensure you are in a quiet environment and have your microphone enabled before starting.</p>
            """
        elif name == "hire":
            title = "Congratulations!"
            content = f"""
                <p>Dear {candidate_name},</p>
                <p>We are delighted to inform you that following your recent interview for the <strong>{job_title}</strong> position, our team has decided to move forward with your application.</p>
                <p>Your background and performance during the session were exceptional, and we believe you would be a fantastic addition to our team. A member of our HR team will contact you shortly to discuss the next steps and provide further details regarding the offer.</p>
                <p>We look forward to potentially working with you!</p>
            """
        elif name == "reject":
            title = "Application Update"
            content = f"""
                <p>Dear {candidate_name},</p>
                <p>Thank you for your interest in the <strong>{job_title}</strong> position and for taking the time to participate in our selection process.</p>
                <p>After careful consideration, we have decided to move forward with other candidates whose qualifications more closely align with our current requirements at this stage.</p>
                <p>We appreciate the time and effort you put into your application and wish you the very best in your professional endeavors.</p>
            """
        elif name == "hold":
            title = "Application Status Update"
            content = f"""
                <p>Dear {candidate_name},</p>
                <p>Thank you for participating in the voice interview for the <strong>{job_title}</strong> role. We wanted to provide a quick update on your application status.</p>
                <p>Our team is still in the process of interviewing candidates. Your application has been placed on hold for further review as we finalize our evaluations. We expect to provide a definitive update within the next few business days.</p>
                <p>Thank you for your patience and continued interest in our company.</p>
            """
        else:
            return ""

        return f"""
        <!DOCTYPE html>
        <html>
        <body style="{base_style}">
            <div style="{container_style}">
                <div style="{header_style}">
                    <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #111827;">{title}</h1>
                </div>
                <div style="{body_style}">
                    {content}
                    <p style="margin-top: 32px; font-weight: 500;">Best regards,<br>The Recruitment Team</p>
                </div>
                <div style="{footer_style}">
                    <p style="margin: 0;">&copy; {datetime.now().year} VoiceHire. This is an automated message, please do not reply directly to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """

    async def _send(self, to_email: str, subject: str, html: str) -> bool:
        """Single internal point of exit with minimal error handling."""
        if not self._connection_string and not (self._endpoint and self._key):
            logger.warning("Email skipping: No credentials configured.")
            return False

        msg = {
            "senderAddress": self._sender_address,
            "recipients": {"to": [{"address": to_email}]},
            "content": {"subject": subject, "html": html}
        }
        
        try:
            client = EmailClient.from_connection_string(self._connection_string) if self._connection_string else \
                     EmailClient(self._endpoint, AzureKeyCredential(self._key))
            
            async with client:
                await client.begin_send(msg)
                logger.info(f"Email '{subject}' sent to {to_email}")
                return True
        except Exception as e:
            logger.error(f"Email failed: {e}")
            return False

    async def send_decision_email(self, candidate_email: str, candidate_name: str, is_eligible: bool, job_title: str = "the position", session_token: str | None = None) -> bool:
        if is_eligible and not session_token: return False
        
        subject = settings.EMAIL_SUBJECT_INTERVIEW_INVITE if is_eligible else settings.EMAIL_SUBJECT_REJECTION
        template = "invite" if is_eligible else "reject"
        html = self._get_template(template, candidate_name=candidate_name, job_title=job_title, session_token=session_token)
        
        return await self._send(candidate_email, subject, html)

    async def send_post_interview_decision(self, email: str, name: str, recommendation: str, job_title: str = "the position") -> bool:

        
        subjects = {
            "hire": settings.EMAIL_SUBJECT_HIRE,
            "reject": settings.EMAIL_SUBJECT_POST_REJECT,
            "hold": settings.EMAIL_SUBJECT_HOLD
        }
        rec = recommendation.lower()
        
        return await self._send(email, subjects.get(rec, settings.EMAIL_SUBJECT_HOLD), self._get_template(rec, candidate_name=name, job_title=job_title))

#instance for easy import
azure_email = AzureEmailManager()