"""CleanLondon notification services."""

from app.database.connection import get_db


def get_my_notifications(user_id: int) -> dict:
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, channel, subject, body, status, created_at, sent_at
                FROM notification_outbox
                WHERE recipient_user_id = %s
                ORDER BY created_at DESC LIMIT 50
                """,
                (user_id,),
            )
            return {"notifications": cursor.fetchall()}
