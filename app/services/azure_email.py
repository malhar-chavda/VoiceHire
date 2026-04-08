import logging
from azure.communication.email.aio import EmailClient
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from app.utils.settings import settings

logger = logging.getLogger(__name__)

async def send_decision_email(candidate_email: str, candidate_name: str, is_eligible: bool, session_token: str = None):
    """
    Sends an automated interview invite or rejection email to a candidate using Azure Communication Services.
    """
    if not settings.AZURE_COMMUNICATION_CONNECTION_STRING:
        logger.warning("Email disabled: AZURE_COMMUNICATION_CONNECTION_STRING is missing in .env")
        return

    if is_eligible:
        interview_url = f"http://localhost:3000/interview/{session_token}"
        subject = "Invitation: Voice Interview"
        html_content = f"""
        <html>
            <body>
                <h2>Congratulations, {candidate_name}!</h2>
                <p>You have been selected to proceed to the next round of our hiring process.</p>
                <p>We invite you to take our AI-driven Voice Interview at your earliest convenience.</p>
                <p><strong><a href="{interview_url}">Click here to start your interview</a></strong></p>
                <br>
                <p>Best regards,</p>
                <p>The Voice Hire Team</p>
            </body>
        </html>
        """
    else:
        subject = "Update on your application"
        html_content = f"""
        <html>
            <body>
                <h2>Hi {candidate_name},</h2>
                <p>Thank you for taking the time to apply for our open position.</p>
                <p>Unfortunately, after carefully reviewing your profile against our current requirements, we will not be moving forward with your application at this time.</p>
                <br>
                <p>We appreciate your interest and wish you the best in your future endeavors.</p>
                <p>Best regards,</p>
                <p>The Voice Hire Team</p>
            </body>
        </html>
        """

    message = {
        "senderAddress": settings.AZURE_SENDER_EMAIL,
        "recipients":  {
            "to": [{"address": candidate_email}],
        },
        "content": {
            "subject": subject,
            "html": html_content,
        }
    }

    try:
        # We instantiate within the block to securely scope the connection lifecycle
        client = EmailClient.from_connection_string(settings.AZURE_COMMUNICATION_CONNECTION_STRING)
        async with client:
            poller = await client.begin_send(message)
            # We don't await the poller result completely to avoid blocking the background task extensively,
            # but we trigger the dispatch. (Or we can await it if we want confirmation logged)
            result = await poller.result()
            logger.info(f"Email sent successfully to {candidate_email}: Message ID {result['messageId']}")
            
    except ResourceNotFoundError as e:
        logger.error(f"Email failed: Azure Communication Service not found. {e}")
    except HttpResponseError as e:
        logger.error(f"Email failed: HTTP error connecting to Azure Email. Code: {e.status_code}")
    except Exception as e:
        logger.error(f"Failed to send email to {candidate_email}: {e}")
