from __future__ import annotations
import logging
from typing import Any
from azure.communication.email.aio import EmailClient
# from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from azure.core.credentials import AzureKeyCredential
from app.utils.settings import settings

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
        """Simple template director to keep logic lean."""
        candidate_name = kwargs.get("candidate_name", "Candidate")
        
        # Invite
        if name == "invite":
            interview_id = kwargs.get('interview_id')
            token = kwargs.get('session_token')
            url = f"{settings.FRONTEND_BASE_URL}/interview.html?token={token}&interview_id={interview_id}"
            return f'<html><body style="font-family: Arial;"><h2>Congrats, {candidate_name}!</h2><p>Click below to start your AI interview:</p><a href="{url}" style="background:#0078d4;color:white;padding:10px;text-decoration:none;border-radius:4px;">Start Interview</a></body></html>'
        
        # Decision
        templates = {
            "hire":   (f"<h2>Great news, {candidate_name}!</h2><p>Your interview was exceptional 🔥🔥. Our team will contact you shortly with an offer.</p>", "#28a745"),
            "reject": (f"<h2>Hi {candidate_name},</h2><p>Thank you for your time. We have decided not to move forward with your application at this stage. But all the best for the future!</p>", "#333"),
            "hold":   (f"<h2>Hi {candidate_name},</h2><p>Your interview is complete. We are still reviewing other candidates and will update you soon.</p>", "#ffc107")
        }
        
        content, border_color = templates.get(name, templates["hold"])
        return f"""
        <html><body style="font-family: Arial; color: #333; line-height: 1.5;">
            <div style="max-width: 500px; padding: 20px; border: 1px solid #eee; border-top: 5px solid {border_color}; border-radius: 8px;">
                {content}
                <p style="font-size: 11px; color: #999; margin-top: 20px;">Best regards,<br>The VoiceHire Team</p>
            </div>
        </body></html>
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

    async def send_decision_email(self, candidate_email: str, candidate_name: str, is_eligible: bool, session_token: str | None = None, interview_id: str | None = None) -> bool:
        if is_eligible and (not session_token or not interview_id): return False
        
        subject = "Invitation: Voice Interview" if is_eligible else "Application Update"
        template = "invite" if is_eligible else "reject"
        html = self._get_template(template, candidate_name=candidate_name, session_token=session_token, interview_id=interview_id)
        
        return await self._send(candidate_email, subject, html)

    async def send_post_interview_decision(self, email: str, name: str, recommendation: str) -> bool:
        from app.utils.settings import EMAIL_SUBJECT_HIRE, EMAIL_SUBJECT_POST_REJECT, EMAIL_SUBJECT_HOLD
        
        subjects = {"hire": EMAIL_SUBJECT_HIRE, "reject": EMAIL_SUBJECT_POST_REJECT, "hold": EMAIL_SUBJECT_HOLD}
        rec = recommendation.lower()
        
        return await self._send(email, subjects.get(rec, EMAIL_SUBJECT_HOLD), self._get_template(rec, candidate_name=name))

#instance for easy import
azure_email = AzureEmailManager()
