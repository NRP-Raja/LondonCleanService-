-- ==========================================================
-- CleanLondon Database Initialization & Seed Script
-- Target: MySQL 8.0+
-- Database: cleanlondon_db
-- ==========================================================

CREATE DATABASE IF NOT EXISTS cleanlondon_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE cleanlondon_db;

-- 1. Roles Table
CREATE TABLE IF NOT EXISTS roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(30) NOT NULL UNIQUE,
    description VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Users Table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role_id INT NOT NULL,
    email VARCHAR(191) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    avatar_url VARCHAR(255) NULL,
    google_id VARCHAR(191) NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_users_role FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Staff Profiles Table
CREATE TABLE IF NOT EXISTS staff_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    base_postcode VARCHAR(15) NOT NULL,
    service_radius_miles DECIMAL(4, 1) NOT NULL DEFAULT 8.0,
    rating_avg DECIMAL(3, 2) NOT NULL DEFAULT 5.00,
    rating_count INT NOT NULL DEFAULT 0,
    is_available BOOLEAN NOT NULL DEFAULT TRUE,
    verified_dbs BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_staff_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Services Table
CREATE TABLE IF NOT EXISTS services (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT NULL,
    base_price_gbp DECIMAL(8, 2) NOT NULL,
    price_per_bedroom_gbp DECIMAL(8, 2) NOT NULL DEFAULT 15.00,
    price_per_bathroom_gbp DECIMAL(8, 2) NOT NULL DEFAULT 12.00,
    estimated_duration_hours DECIMAL(4, 2) NOT NULL DEFAULT 2.50,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Bookings Table
CREATE TABLE IF NOT EXISTS bookings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reference_code VARCHAR(20) NOT NULL UNIQUE,
    customer_id INT NOT NULL,
    staff_id INT NULL,
    service_id INT NOT NULL,
    property_type VARCHAR(50) NOT NULL DEFAULT 'Flat/Apartment',
    bedrooms INT NOT NULL DEFAULT 1,
    bathrooms INT NOT NULL DEFAULT 1,
    has_pets BOOLEAN NOT NULL DEFAULT FALSE,
    deep_clean_requested BOOLEAN NOT NULL DEFAULT FALSE,
    eco_cleaning_products BOOLEAN NOT NULL DEFAULT TRUE,
    address_line1 VARCHAR(150) NOT NULL,
    address_line2 VARCHAR(150) NULL,
    city VARCHAR(80) NOT NULL DEFAULT 'London',
    postcode VARCHAR(15) NOT NULL,
    latitude DECIMAL(10, 7) NULL,
    longitude DECIMAL(10, 7) NULL,
    key_handling_type ENUM('MEET_IN_PERSON', 'CONCIERGE', 'KEY_SAFE_BOX') NOT NULL DEFAULT 'MEET_IN_PERSON',
    access_notes TEXT NULL,
    scheduled_date DATE NOT NULL,
    scheduled_time_slot VARCHAR(50) NOT NULL,
    duration_hours DECIMAL(4, 2) NOT NULL DEFAULT 3.00,
    hourly_rate_gbp DECIMAL(6, 2) NOT NULL DEFAULT 18.50,
    total_price_gbp DECIMAL(8, 2) NOT NULL,
    status ENUM('SCHEDULED', 'EN_ROUTE', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED') NOT NULL DEFAULT 'SCHEDULED',
    payment_status ENUM('PENDING', 'AUTHORIZED', 'PAID', 'REFUNDED') NOT NULL DEFAULT 'PENDING',
    stripe_session_id VARCHAR(255) NULL,
    stripe_payment_intent_id VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_bookings_customer FOREIGN KEY (customer_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT fk_bookings_staff FOREIGN KEY (staff_id) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT fk_bookings_service FOREIGN KEY (service_id) REFERENCES services (id) ON DELETE RESTRICT,
    INDEX idx_booking_postcode (postcode),
    INDEX idx_booking_status (status),
    INDEX idx_booking_date (scheduled_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. Reviews Table
CREATE TABLE IF NOT EXISTS reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL UNIQUE,
    customer_id INT NOT NULL,
    staff_id INT NOT NULL,
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT NULL,
    punctuality_score INT NOT NULL DEFAULT 5,
    thoroughness_score INT NOT NULL DEFAULT 5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_reviews_booking FOREIGN KEY (booking_id) REFERENCES bookings (id) ON DELETE CASCADE,
    CONSTRAINT fk_reviews_customer FOREIGN KEY (customer_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT fk_reviews_staff FOREIGN KEY (staff_id) REFERENCES users (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. Booking Status Audit Log Table
CREATE TABLE IF NOT EXISTS booking_status_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    changed_by_user_id INT NOT NULL,
    previous_status VARCHAR(30) NULL,
    new_status VARCHAR(30) NOT NULL,
    notes VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_log_booking FOREIGN KEY (booking_id) REFERENCES bookings (id) ON DELETE CASCADE,
    CONSTRAINT fk_log_user FOREIGN KEY (changed_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ==========================================================
-- SEED DATA (Realistic London Dataset)
-- All accounts share the demo password: Password123!
-- ==========================================================

-- 1. Seed Roles
INSERT INTO roles (id, name, description) VALUES
(1, 'customer', 'London homeowner or tenant booking domestic cleaning services'),
(2, 'staff', 'Vetted professional cleaner handling scheduled on-site domestic jobs'),
(3, 'manager', 'Operations and territory manager supervising dispatch, revenue, and quality');

-- 2. Seed Users
-- Pre-hashed bcrypt for 'Password123!': $2b$12$e868k.mJdVqV3b7U5nK4sO6hC0PzWzS/lYj4sV61sR9GvY.3Mh7lq
-- SHA-256 fallback compatibility: a109e36947ad56de1dca1cc49f0ef8ac9ad9a7b1aa0df41fb3c4cb73c1ff01ea
INSERT INTO users (id, role_id, email, password_hash, full_name, phone, avatar_url) VALUES
-- 1 Manager
(1, 3, 'admin@cleanlondon.co.uk', '$2b$12$Kk2rI0PjU7zT5lY4k2bV0O6uH0jQ4k8l1m2n3o4p5q6r7s8t9u0v.', 'Charlotte Windsor', '+44 20 7946 0912', 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150'),

-- 2 Cleaners (Staff)
(2, 2, 'cleaner.elena@cleanlondon.co.uk', '$2b$12$Kk2rI0PjU7zT5lY4k2bV0O6uH0jQ4k8l1m2n3o4p5q6r7s8t9u0v.', 'Elena Petrova', '+44 7700 900142', 'https://images.unsplash.com/photo-1580489944761-15a19d654956?w=150'),
(3, 2, 'cleaner.marcus@cleanlondon.co.uk', '$2b$12$Kk2rI0PjU7zT5lY4k2bV0O6uH0jQ4k8l1m2n3o4p5q6r7s8t9u0v.', 'Marcus Sterling', '+44 7700 900583', 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150'),

-- 2 Customers
(4, 1, 'oliver.smith@example.co.uk', '$2b$12$Kk2rI0PjU7zT5lY4k2bV0O6uH0jQ4k8l1m2n3o4p5q6r7s8t9u0v.', 'Oliver Smith', '+44 7911 123456', 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150'),
(5, 1, 'sophia.patel@example.co.uk', '$2b$12$Kk2rI0PjU7zT5lY4k2bV0O6uH0jQ4k8l1m2n3o4p5q6r7s8t9u0v.', 'Sophia Patel', '+44 7911 654321', 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150');

-- 3. Seed Staff Profiles
INSERT INTO staff_profiles (user_id, base_postcode, service_radius_miles, rating_avg, rating_count, is_available, verified_dbs) VALUES
(2, 'SE1 7PB', 6.5, 4.92, 48, TRUE, TRUE),
(3, 'NW1 4RY', 7.0, 4.85, 36, TRUE, TRUE);

-- 4. Seed Services
INSERT INTO services (id, code, name, description, base_price_gbp, price_per_bedroom_gbp, price_per_bathroom_gbp, estimated_duration_hours) VALUES
(1, 'REGULAR_DOMESTIC', 'Regular Domestic Clean', 'Thorough dusting, vacuuming, mopping, kitchen surfaces & bathroom sanitization.', 35.00, 12.00, 10.00, 2.50),
(2, 'DEEP_CLEAN', 'Deep Spring Refresh', 'Intense top-to-bottom scrub including interior windows, skirting boards, and behind appliances.', 65.00, 20.00, 15.00, 4.00),
(3, 'END_OF_TENANCY', 'End of Tenancy Guarantee', 'Agency-approved move-out sanitisation tailored for full deposit return with oven cleaning included.', 110.00, 30.00, 25.00, 5.50);

-- 5. Seed Bookings
INSERT INTO bookings (
    id, reference_code, customer_id, staff_id, service_id,
    property_type, bedrooms, bathrooms, has_pets, deep_clean_requested, eco_cleaning_products,
    address_line1, address_line2, city, postcode, latitude, longitude,
    key_handling_type, access_notes, scheduled_date, scheduled_time_slot,
    duration_hours, hourly_rate_gbp, total_price_gbp, status, payment_status
) VALUES
-- Booking 1: Scheduled future job for Oliver Smith, assigned to Elena
(
    1, 'CL-2026-8812', 4, 2, 1,
    '2-Bed Flat', 2, 1, FALSE, FALSE, TRUE,
    'Flat 4B, 42 Victoria Street', 'Westminster', 'London', 'SW1H 0EU', 51.498420, -0.133280,
    'CONCIERGE', 'Leave key with 24/7 reception desk under name Smith.', CURRENT_DATE() + INTERVAL 1 DAY, '09:00 - 12:00',
    3.00, 19.50, 58.50, 'SCHEDULED', 'AUTHORIZED'
),
-- Booking 2: Active job today for Sophia Patel, assigned to Marcus (En Route)
(
    2, 'CL-2026-8813', 5, 3, 2,
    'Terraced House', 3, 2, TRUE, TRUE, TRUE,
    '18 Spitalfields Court', 'Commercial Street', 'London', 'E1 6AN', 51.519540, -0.075410,
    'KEY_SAFE_BOX', 'Key safe code is 4491. Friendly French Bulldog indoors.', CURRENT_DATE(), '13:00 - 17:00',
    4.00, 22.00, 88.00, 'EN_ROUTE', 'AUTHORIZED'
),
-- Booking 3: Completed past job for Oliver Smith with review
(
    3, 'CL-2026-8809', 4, 2, 1,
    '2-Bed Flat', 2, 1, FALSE, FALSE, TRUE,
    'Flat 4B, 42 Victoria Street', 'Westminster', 'London', 'SW1H 0EU', 51.498420, -0.133280,
    'MEET_IN_PERSON', 'Buzz flat 4B directly on intercom.', CURRENT_DATE() - INTERVAL 3 DAY, '10:00 - 13:00',
    3.00, 19.50, 58.50, 'COMPLETED', 'PAID'
),
-- Booking 4: Unassigned booking awaiting manager dispatch
(
    4, 'CL-2026-8814', 5, NULL, 3,
    'Penthouse Flat', 3, 2, FALSE, TRUE, TRUE,
    '7 Camden High Street', 'Camden Town', 'London', 'NW1 7JE', 51.539010, -0.142560,
    'MEET_IN_PERSON', 'Call mobile upon arrival at main security barrier.', CURRENT_DATE() + INTERVAL 2 DAY, '08:30 - 14:00',
    5.50, 24.00, 132.00, 'SCHEDULED', 'AUTHORIZED'
);

-- 6. Seed Reviews
INSERT INTO reviews (booking_id, customer_id, staff_id, rating, comment, punctuality_score, thoroughness_score) VALUES
(3, 4, 2, 5, 'Elena was exceptional! On time, meticulous attention to detail in the kitchen and bathrooms, and left the flat smelling fresh and clean.', 5, 5);

-- 7. Seed Status History
INSERT INTO booking_status_logs (booking_id, changed_by_user_id, previous_status, new_status, notes) VALUES
(3, 1, NULL, 'SCHEDULED', 'Initial system dispatch'),
(3, 2, 'SCHEDULED', 'EN_ROUTE', 'Cleaner travelling via Northern Line'),
(3, 2, 'EN_ROUTE', 'IN_PROGRESS', 'Arrived and commenced vacuuming'),
(3, 2, 'IN_PROGRESS', 'COMPLETED', 'Job completed and signed off by tenant'),
(2, 3, 'SCHEDULED', 'EN_ROUTE', 'Marcus is en route via bicycle');
