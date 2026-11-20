"""CleanLondon additive operational database migrations."""

from app.core.config import DB_NAME
from app.database.connection import get_db
from app.utils.encryption import encrypt_sensitive_data, decrypt_sensitive_data
from cryptography.fernet import InvalidToken


def ensure_operational_schema() -> None:
    """Apply additive schema changes to existing Docker volumes."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'staff_profiles'
                """,
                (DB_NAME,),
            )
            existing_columns = {row["COLUMN_NAME"] for row in cursor.fetchall()}
            additions = {
                "right_to_work_verified": "BOOLEAN NOT NULL DEFAULT TRUE",
                "vetting_status": "ENUM('PENDING', 'APPROVED', 'REJECTED') NOT NULL DEFAULT 'APPROVED'",
                "dbs_document_ref": "VARCHAR(255) NULL",
                "right_to_work_document_ref": "VARCHAR(255) NULL",
                "vetted_at": "TIMESTAMP NULL",
            }
            for column, definition in additions.items():
                if column not in existing_columns:
                    cursor.execute(f"ALTER TABLE staff_profiles ADD COLUMN {column} {definition}")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS staff_weekly_availability (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    staff_id INT NOT NULL,
                    day_of_week TINYINT NOT NULL,
                    start_time TIME NOT NULL,
                    end_time TIME NOT NULL,
                    UNIQUE KEY uq_staff_weekly_slot (staff_id, day_of_week),
                    CONSTRAINT fk_weekly_staff FOREIGN KEY (staff_id) REFERENCES users (id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS staff_holidays (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    staff_id INT NOT NULL,
                    holiday_date DATE NOT NULL,
                    reason VARCHAR(255) NULL,
                    UNIQUE KEY uq_staff_holiday (staff_id, holiday_date),
                    CONSTRAINT fk_holiday_staff FOREIGN KEY (staff_id) REFERENCES users (id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_outbox (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    recipient_user_id INT NULL,
                    recipient_address VARCHAR(255) NOT NULL,
                    channel ENUM('EMAIL', 'SMS') NOT NULL DEFAULT 'EMAIL',
                    subject VARCHAR(255) NOT NULL,
                    body TEXT NOT NULL,
                    status ENUM('QUEUED', 'SENT', 'FAILED') NOT NULL DEFAULT 'QUEUED',
                    error_message VARCHAR(500) NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sent_at TIMESTAMP NULL,
                    is_read BOOLEAN NOT NULL DEFAULT FALSE,
                    priority ENUM('LOW','NORMAL','HIGH','CRITICAL') NOT NULL DEFAULT 'NORMAL',
                    deep_link VARCHAR(255) NULL,
                    CONSTRAINT fk_notification_user FOREIGN KEY (recipient_user_id) REFERENCES users (id) ON DELETE SET NULL,
                    INDEX idx_notification_recipient (recipient_user_id, created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                ALTER TABLE bookings MODIFY COLUMN status
                ENUM('PENDING','APPROVED','CONFIRMED','SCHEDULED','EN_ROUTE','IN_PROGRESS','COMPLETED','REJECTED','CANCELLED')
                NOT NULL DEFAULT 'SCHEDULED'
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS payment_records (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    booking_id INT NOT NULL,
                    amount_gbp DECIMAL(8,2) NOT NULL,
                    method ENUM('CASH','CARD','BANK_TRANSFER','REFUND','OTHER') NOT NULL,
                    status ENUM('RECORDED','VERIFIED','REFUND_REQUESTED','REFUNDED','REJECTED') NOT NULL DEFAULT 'RECORDED',
                    reference VARCHAR(100) NULL,
                    recorded_by INT NOT NULL,
                    verified_by INT NULL,
                    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    verified_at TIMESTAMP NULL,
                    CONSTRAINT fk_payment_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT,
                    CONSTRAINT fk_payment_recorded_by FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT,
                    CONSTRAINT fk_payment_verified_by FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT,
                    INDEX idx_payment_booking (booking_id, recorded_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS support_cases (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    booking_id INT NULL,
                    customer_id INT NOT NULL,
                    assigned_to INT NULL,
                    subject VARCHAR(160) NOT NULL,
                    description TEXT NOT NULL,
                    status ENUM('OPEN','IN_PROGRESS','RESOLVED') NOT NULL DEFAULT 'OPEN',
                    outcome TEXT NULL,
                    follow_up_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    CONSTRAINT fk_support_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE SET NULL,
                    CONSTRAINT fk_support_customer FOREIGN KEY (customer_id) REFERENCES users(id) ON DELETE RESTRICT,
                    CONSTRAINT fk_support_assignee FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_audit_log (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    actor_id INT NULL,
                    actor_role VARCHAR(30) NULL,
                    action VARCHAR(80) NOT NULL,
                    entity_type VARCHAR(80) NOT NULL,
                    entity_id VARCHAR(100) NULL,
                    before_json JSON NULL,
                    after_json JSON NULL,
                    reason VARCHAR(500) NULL,
                    request_id VARCHAR(100) NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_audit_entity (entity_type, entity_id),
                    INDEX idx_audit_actor (actor_id, created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS staff_shifts (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    staff_id INT NOT NULL,
                    shift_date DATE NOT NULL,
                    start_time TIME NOT NULL,
                    end_time TIME NOT NULL,
                    status ENUM('PLANNED','CONFIRMED','CANCELLED') NOT NULL DEFAULT 'PLANNED',
                    created_by INT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_staff_shift_slot (staff_id, shift_date, start_time, end_time),
                    CONSTRAINT fk_shift_staff FOREIGN KEY (staff_id) REFERENCES users(id) ON DELETE CASCADE,
                    CONSTRAINT fk_shift_creator FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS staff_time_off (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    staff_id INT NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    reason VARCHAR(255) NULL,
                    status ENUM('PENDING','APPROVED','REJECTED') NOT NULL DEFAULT 'PENDING',
                    reviewed_by INT NULL,
                    reviewed_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_timeoff_staff FOREIGN KEY (staff_id) REFERENCES users(id) ON DELETE CASCADE,
                    CONSTRAINT fk_timeoff_reviewer FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS business_settings (
                    setting_key VARCHAR(100) PRIMARY KEY,
                    setting_value JSON NOT NULL,
                    updated_by INT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    CONSTRAINT fk_settings_updater FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS expenses (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    expense_date DATE NOT NULL,
                    category VARCHAR(80) NOT NULL,
                    amount_gbp DECIMAL(10,2) NOT NULL,
                    description VARCHAR(255) NULL,
                    recorded_by INT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_expense_recorded_by FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

            cursor.execute(
                """
                SELECT id, access_notes
                FROM bookings
                WHERE access_notes IS NOT NULL AND TRIM(access_notes) <> ''
                """
            )
            for booking in cursor.fetchall():
                try:
                    decrypt_sensitive_data(booking["access_notes"])
                    continue
                except (InvalidToken, RuntimeError, ValueError, TypeError):
                    encrypted = encrypt_sensitive_data(booking["access_notes"])
                    cursor.execute(
                        "UPDATE bookings SET access_notes = %s WHERE id = %s",
                        (encrypted, booking["id"]),
                    )

            valid_demo_hash = "$2b$12$Ww6zkTlA7XwpVflMIq1aRuvMunTakRHn3ShYtgTFF//GWiEmZRjNq"
            cursor.execute(
                """
                UPDATE users
                SET password_hash = %s
                WHERE password_hash = '$2b$12$Kk2rI0PjU7zT5lY4k2bV0O6uH0jQ4k8l1m2n3o4p5q6r7s8t9u0v.'
                """,
                (valid_demo_hash,),
            )
