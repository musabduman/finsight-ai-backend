# db.py — Ortak veritabanı yardımcıları (bağlantı, şifre hashleme, migration)
#
# Eskiden db_server.py içindeydi. main.py ve routers/auth.py tarafından
# ortak kullanılıyor.

import os
import bcrypt
import hashlib
import psycopg2

from dotenv import load_dotenv
from fastapi import HTTPException
from psycopg2.extras import RealDictCursor

load_dotenv()
DATABASE_URL = os.getenv("DB_LINK")


def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


# ---------------------------
# ŞİFRE HASHLEME (bcrypt)
# ---------------------------
def hash_password(plain_password: str) -> str:
    sha256_hash = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    hashed_bytes = bcrypt.hashpw(sha256_hash.encode('utf-8'), bcrypt.gensalt())
    return hashed_bytes.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    sha256_hash = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    return bcrypt.checkpw(sha256_hash.encode('utf-8'), hashed_password.encode('utf-8'))


def _dogrula(cursor, email: str, password: str):
    """Email + şifre eşleşiyorsa devam eder, yoksa 401 fırlatır."""
    cursor.execute("SELECT password FROM users WHERE email=%s", (email,))
    row = cursor.fetchone()
    if not row or not verify_password(password, row["password"]):
        raise HTTPException(status_code=401, detail="E-posta veya şifre hatalı.")


# ---------------------------
# TABLO OLUŞTURMA + MİGRASYON
# ---------------------------
def init_db():
    conn   = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                SERIAL PRIMARY KEY,
            username          TEXT UNIQUE,
            email             TEXT UNIQUE,
            password          TEXT,
            gemini_key        TEXT DEFAULT '',
            ollama_key        TEXT DEFAULT '',
            is_verified       INTEGER DEFAULT 1,
            verification_code TEXT
        )
    """)

    cursor.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='groq_key'
            ) THEN
                ALTER TABLE users RENAME COLUMN groq_key TO ollama_key;
            END IF;
        END$$;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id     SERIAL PRIMARY KEY,
            email  TEXT,
            symbol TEXT,
            UNIQUE(email, symbol)
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()