# routers/auth.py — Kullanıcı kayıt/giriş, API key yönetimi, izleme listesi
#
# Eskiden db_server.py adında bağımsız bir Render servisiydi.
# main.py'ye APIRouter olarak bağlanıyor.

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from psycopg2 import IntegrityError

from db import get_db_connection, hash_password, verify_password, _dogrula

router = APIRouter()

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
    password:str

class UpdateKeys(BaseModel):
    email:      str
    password:   str   # güvenlik: key güncellemek için şifre gerekli
    gemini_key: str
    ollama_key: str

class ChangePassword(BaseModel):
    email:        str
    old_password: str
    new_password: str

class DeleteRequest(BaseModel):
    email:    str
    password: str   # güvenlik: silmek için şifre gerekli

class GetKeysRequest(BaseModel):
    email:    str
    password: str   # güvenlik: key almak için şifre gerekli


# ---------------------------
# KAYIT
# ---------------------------
@router.post("/register")
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
@router.post("/login")
def login(user: UserLogin):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT email, username, password FROM users WHERE (email=%s OR username=%s)",
            (user.kullanici_bilgisi, user.kullanici_bilgisi)
        )
        db_user = cursor.fetchone()

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
# API KEY OKUMA (şifre zorunlu)
# ---------------------------
@router.post("/get_keys")
def get_keys(req: GetKeysRequest):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        _dogrula(cursor, req.email, req.password)

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
# API KEY GÜNCELLEME (şifre zorunlu)
# ---------------------------
@router.post("/update_keys")
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
@router.post("/change_password")
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
@router.post("/add_watchlist")
def add_watchlist(item: WatchlistItem):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        _dogrula(cursor, item.email, item.password)
        cursor.execute(
            "INSERT INTO watchlist (email, symbol) VALUES (%s, %s)",
            (item.email, item.symbol.upper())
        )
        conn.commit()
        return {"mesaj": f"{item.symbol.upper()} eklendi."}
    except HTTPException:
        raise
    except IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Bu hisse zaten listenizde var!")
    finally:
        cursor.close()
        conn.close()

@router.get("/get_watchlist/{email}")
def get_watchlist(email: str, password: str):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        _dogrula(cursor, email, password)
        cursor.execute("SELECT symbol FROM watchlist WHERE email=%s", (email,))
        symbols = [row["symbol"] for row in cursor.fetchall()]
        return {"watchlist": symbols}
    finally:
        cursor.close()
        conn.close()

@router.delete("/remove_watchlist/{email}/{symbol}")
def remove_watchlist(email: str, symbol: str, password: str):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        _dogrula(cursor, email, password)
        cursor.execute(
            "DELETE FROM watchlist WHERE email=%s AND symbol=%s",
            (email, symbol.upper())
        )
        conn.commit()
        return {"mesaj": f"{symbol.upper()} çıkarıldı."}
    finally:
        cursor.close()
        conn.close()

@router.delete("/clear_watchlist")
def clear_watchlist(req: DeleteRequest):
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


@router.delete("/delete_account")
def delete_account(req: DeleteRequest):
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