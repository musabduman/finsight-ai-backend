# db_server.py — FinSight AI Veritabanı Sunucusu (Render)
#
# DÜZELTMELER:
# 1. SHA-256 → bcrypt (salt'lı, güvenli şifre hash'i)
# 2. /get_keys artık şifre doğrulaması istiyor (email+şifre olmadan key alınamaz)
# 3. /delete_account ve /clear_watchlist artık şifre doğrulaması istiyor
# 4. groq_key sütunu → ollama_key olarak yeniden adlandırıldı (migration ile)
# 5. CORS eklendi (db_server da dışarıya açıksa gerekli)
import os
import bcrypt
import hashlib
import psycopg2

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor
from psycopg2 import IntegrityError

app = FastAPI(title="FinSight AI Database Server")

origins = [
    "http://localhost:3000", # Lokal testler için
    "https://finsight-ai-frontend-lihbtxwsy-musabdumans-projects.vercel.app", # Vercel linkin (kendi linkinle değiştir)
]

# CORS — sadece kendi frontend domain'ini yaz, production'da "*" olmamalı
# Geliştirme aşamasındaysan ["*"] bırakabilirsin, deploy öncesi değiştir
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# ŞİFRE HASHLEME  (bcrypt)
# ---------------------------
# bcrypt her şifre için otomatik rastgele salt üretir.
# Eski SHA-256 hash'leri artık çalışmaz — mevcut kullanıcılar
# şifrelerini sıfırlamak zorunda kalır. Eğer mevcut kullanıcı
# yoksa (yeni proje) hiçbir şey değişmez.

def hash_password(plain_password: str) -> str:
    # 1. Şifreyi SHA-256 ile hash'le
    sha256_hash = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    # 2. Bcrypt ile tuzla (Bu işlem bytes döndürür)
    hashed_bytes = bcrypt.hashpw(sha256_hash.encode('utf-8'), bcrypt.gensalt())
    # 3. Veritabanı TEXT sütununa sorunsuz kaydetmek için string'e çevirip döndür
    return hashed_bytes.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # 1. Girilen şifreyi SHA-256'ya çevir
    sha256_hash = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    # 2. Hem girilen şifreyi hem de veritabanından gelen string'i bytes'a çevirerek karşılaştır
    return bcrypt.checkpw(sha256_hash.encode('utf-8'), hashed_password.encode('utf-8'))

# ---------------------------
# VERİTABANI BAĞLANTISI
# ---------------------------
load_dotenv()
DATABASE_URL = os.getenv("DB_LINK")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# ---------------------------
# TABLO OLUŞTURMA + MİGRASYON
# ---------------------------
def init_db():
    conn   = get_db_connection()
    cursor = conn.cursor()

    # Kullanıcı tablosu
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

    # Eski veritabanında sütun adı groq_key ise ollama_key'e yeniden adlandır
    # Bu satır ilk çalışmada migration yapar, sonraki çalışmalarda hata vermez
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

    # İzleme listesi tablosu
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

@app.on_event("startup")
def startup():
    init_db()

# ---------------------------
# VERİ MODELLERİ
# ---------------------------
class UserRegister(BaseModel):
    username:    str
    email:       str
    password:    str
    gemini_key:  str = ""
    ollama_key:  str = ""

class UserLogin(BaseModel):
    kullanici_bilgisi: str
    password:          str

class WatchlistItem(BaseModel):
    email:  str
    symbol: str

class UpdateKeys(BaseModel):
    email:      str
    password:   str   # ← güvenlik: key güncellemek için şifre gerekli
    gemini_key: str
    ollama_key: str

class ChangePassword(BaseModel):
    email:        str
    old_password: str
    new_password: str

class DeleteRequest(BaseModel):
    email:    str
    password: str   # ← güvenlik: silmek için şifre gerekli

class GetKeysRequest(BaseModel):
    email:    str
    password: str   # ← güvenlik: key almak için şifre gerekli

# ---------------------------
# YARDIMCI: Kullanıcı doğrula
# ---------------------------
def _dogrula(cursor, email: str, password: str):
    """
    Email + şifre eşleşiyorsa True döner, yoksa HTTPException fırlatır.
    Tekrar eden doğrulama kodunu her endpoint'e yazmamak için.
    """
    cursor.execute("SELECT password FROM users WHERE email=%s", (email,))
    row = cursor.fetchone()
    if not row or not verify_password(password, row["password"]):
        raise HTTPException(status_code=401, detail="E-posta veya şifre hatalı.")

# ---------------------------
# KAYIT
# ---------------------------
@app.post("/register")
def register(user: UserRegister):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE username=%s", (user.username,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Bu kullanıcı adı alınmış.")

        cursor.execute("SELECT id FROM users WHERE email=%s", (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Bu e-posta zaten kayıtlı.")

        cursor.execute(
            """INSERT INTO users
               (username, email, password, gemini_key, ollama_key, is_verified, verification_code)
               VALUES (%s, %s, %s, %s, %s, 1, 'BYPASS')""",
            (user.username, user.email, hash_password(user.password),
             user.gemini_key, user.ollama_key)
        )
        conn.commit()
        return {"mesaj": "Kayıt başarılı! Giriş yapabilirsiniz.", "kod": 200}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Sunucu hatası: {str(e)}")
    finally:
        cursor.close()
        conn.close()

# ---------------------------
# GİRİŞ
# ---------------------------
@app.post("/login")
def login(user: UserLogin):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT email, username, password FROM users WHERE (email=%s OR username=%s)",
            (user.kullanici_bilgisi, user.kullanici_bilgisi)
        )
        db_user = cursor.fetchone()

        # Kullanıcı bulunamadı veya şifre yanlış
        if not db_user or not verify_password(user.password, db_user["password"]):
            raise HTTPException(status_code=401, detail="Hatalı bilgi veya şifre!")

        return {
            "mesaj":    "Giriş başarılı",
            "email":    db_user["email"],
            "username": db_user["username"],
        }
    finally:
        cursor.close()
        conn.close()

# ---------------------------
# API KEY OKUMA  (şifre zorunlu)
# ---------------------------
@app.post("/get_keys")
def get_keys(req: GetKeysRequest):
    """
    NEDEN POST ve NEDEN ŞİFRE?
    GET /get_keys/email@mail.com olsaydı, email bilen herkes
    başkasının API key'lerini çekebilirdi. Şimdi email + şifre
    ikisi de doğru olmalı.
    """
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        _dogrula(cursor, req.email, req.password)   # şifre yanlışsa burada durur

        cursor.execute(
            "SELECT gemini_key, ollama_key FROM users WHERE email=%s",
            (req.email,)
        )
        keys = cursor.fetchone()
        if not keys:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

        return {"gemini_key": keys["gemini_key"], "ollama_key": keys["ollama_key"]}

    finally:
        cursor.close()
        conn.close()

# ---------------------------
# API KEY GÜNCELLEME  (şifre zorunlu)
# ---------------------------
@app.post("/update_keys")
def update_keys(req: UpdateKeys):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        _dogrula(cursor, req.email, req.password)

        cursor.execute(
            "UPDATE users SET gemini_key=%s, ollama_key=%s WHERE email=%s",
            (req.gemini_key, req.ollama_key, req.email)
        )
        conn.commit()
        return {"message": "API anahtarları başarıyla güncellendi."}

    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Anahtarlar güncellenemedi.")
    finally:
        cursor.close()
        conn.close()

# ---------------------------
# ŞİFRE DEĞİŞTİR
# ---------------------------
@app.post("/change_password")
def change_password(req: ChangePassword):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        _dogrula(cursor, req.email, req.old_password)

        cursor.execute(
            "UPDATE users SET password=%s WHERE email=%s",
            (hash_password(req.new_password), req.email)
        )
        conn.commit()
        return {"message": "Şifreniz başarıyla güncellendi."}

    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        raise HTTPException(status_code=500, detail="İşlem başarısız.")
    finally:
        cursor.close()
        conn.close()

# ---------------------------
# İZLEME LİSTESİ
# ---------------------------
@app.post("/add_watchlist")
def add_watchlist(item: WatchlistItem):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO watchlist (email, symbol) VALUES (%s, %s)",
            (item.email, item.symbol.upper())
        )
        conn.commit()
        return {"mesaj": f"{item.symbol.upper()} eklendi."}
    except IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Bu hisse zaten listenizde var!")
    finally:
        cursor.close()
        conn.close()

@app.get("/get_watchlist/{email}")
def get_watchlist(email: str):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT symbol FROM watchlist WHERE email=%s", (email,))
        symbols = [row["symbol"] for row in cursor.fetchall()]
        return {"watchlist": symbols}
    finally:
        cursor.close()
        conn.close()

@app.delete("/remove_watchlist/{email}/{symbol}")
def remove_watchlist(email: str, symbol: str):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM watchlist WHERE email=%s AND symbol=%s",
            (email, symbol.upper())
        )
        conn.commit()
        return {"mesaj": f"{symbol.upper()} çıkarıldı."}
    finally:
        cursor.close()
        conn.close()

@app.delete("/clear_watchlist")
def clear_watchlist(req: DeleteRequest):
    """
    Tüm izleme listesini sil — şifre doğrulaması zorunlu.
    """
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        _dogrula(cursor, req.email, req.password)
        cursor.execute("DELETE FROM watchlist WHERE email=%s", (req.email,))
        conn.commit()
        return {"message": "İzleme listesi temizlendi."}
    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Liste temizlenemedi.")
    finally:
        cursor.close()
        conn.close()

@app.delete("/delete_account")
def delete_account(req: DeleteRequest):
    """
    Hesabı sil — şifre doğrulaması zorunlu.
    """
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        _dogrula(cursor, req.email, req.password)
        cursor.execute("DELETE FROM watchlist WHERE email=%s", (req.email,))
        cursor.execute("DELETE FROM users WHERE email=%s",     (req.email,))
        conn.commit()
        return {"message": "Hesap başarıyla silindi."}
    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Hesap silinemedi.")
    finally:
        cursor.close()
        conn.close()