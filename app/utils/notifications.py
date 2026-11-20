"""CleanLondon Notification Utilities — queue notification and activity logging."""

from typing import Optional


def queue_notification(
    cursor,
    recipient_user_id: int,
    recipient_email: str,
    subject: str,
    body: str,
    channel: str = "email",
) -> None:
    """Queue a notification in the notification_outbox table."""
    cursor.execute(
        """
        INSERT INTO notification_outbox (recipient_user_id, recipient_email, channel, subject, body, status)
        VALUES (%s, %s, %s, %s, %s, 'PENDING')
        """,
        (recipient_user_id, recipient_email, channel, subject, body),
    )


def log_activity(
    cursor,
    user_id: int,
    action: str,
    details: Optional[str] = None,
) -> None:
    """Log an activity in the audit_log table."""
    cursor.execute(
        """
        INSERT INTO audit_log (user_id, action, details, created_at)
        VALUES (%s, %s, %s, NOW())
        """,
        (user_id, action, details),
    )
