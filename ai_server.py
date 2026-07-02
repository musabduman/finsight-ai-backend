# ai_server.py — FinSight AI Analiz Sunucusu
#
# DÜZELTMELER:
# 1. /api/news artık haber listesi döndürüyor (tüm haberleri tek string'e kesmiyoruz)
# 2. haber.py'den get_hisse_haberleri import edildi
# 3. CORS açıklaması eklendi

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

from anlysis_engine import tek_hisse_run
from ai.llm import Gemini, OllamaAgresif, OllamaChat
from ai.pythorc import deeplearning
from indicators.technical import teknik_analiz
from services.veri import get_stock, normalize_symbol
from services.haber import anlik_hisse_haberi_cek, get_hisse_haberleri

app = FastAPI(title="FinSight AI API")

# --- CORS ---
# Geliştirme aşamasında ["*"] bırakabilirsin.
# Production'a almadan önce kendi frontend URL'ini yaz:
origins = [
    "https://finsight-frontend.onrender.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,   # TODO: deploy öncesi kısıtla
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODEL YÜKLEME ---
# Sunucu başlarken PyTorch modelini hafızaya alıyoruz.
# dl_bot burada global — analiz_et() içinde self.df gibi instance
# state tutuluyorsa eş zamanlı isteklerde sorun çıkabilir.
# Şimdilik tek kullanıcılı/az trafikli proje için sorunsuz.
dl_bot = deeplearning()

# --- PYDANTIC VERİ MODELLERİ ---
class AnalizIstegi(BaseModel):
    sembol:     str
    gemini_key: str
    ollama_key: str

class ChatMesaji(BaseModel):
    role:    str
    content: str

class ChatIstegi(BaseModel):
    messages: List[ChatMesaji]
    baglam:   str
    ollama_key: str

# --- ENDPOINTLERİ ---

@app.post("/api/analyze")
async def analyze_stock(istek: AnalizIstegi):
    """
    Detaylı hisse analizi: teknik analiz + DL tahmini + Gemini + Ollama raporu.
    """
    try:
        gemini_bot = Gemini(api_key=istek.gemini_key)
        ollama_bot = OllamaAgresif(api_key=istek.ollama_key)

        sonuc = tek_hisse_run(
            sembol=istek.sembol.upper(),
            dl_bot=dl_bot,
            gemini_bot=gemini_bot,
            ollama_bot=ollama_bot,
        )

        if "error" in sonuc:
            raise HTTPException(status_code=400, detail=sonuc["error"])

        df_out = sonuc["df"]
        if df_out is None or df_out.empty:
            raise HTTPException(status_code=400, detail="Teknik veri DataFrame'i boş döndü.")

        son_satir = df_out.iloc[-1]

        return {
            "symbol":    sonuc["symbol"],
            "son_fiyat": float(sonuc["son_fiyat"]),
            "degisim":   round(float(son_satir.get("Percent_Change", 0.0)), 2),
            "sbs":       round(float(sonuc["son_sbs"]), 1),
            "rsi":       round(float(son_satir.get("RSI", 50.0)), 1),
            "karar":     sonuc["dl"].get("yön", "Nötr"),
            "gemini":    sonuc["gemini"],
            "ollama":    sonuc["ollama"],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat_bot(istek: ChatIstegi):
    """AI Asistan: sohbet geçmişi ve aktif bağlamla cevap üretir."""
    try:
        chat_ai = OllamaChat(api_key=istek.ollama_key)
        gecmis  = [{"role": m.role, "content": m.content} for m in istek.messages]
        cevap   = chat_ai.generate(chat_history=gecmis, aktif_baglam=istek.baglam)
        return {"cevap": cevap}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/quick-scan/{sembol}")
async def quick_scan(sembol: str):
    """
    Mega Tarama / BIST30 için hızlı teknik + DL tarama.
    Her hisse için ayrı ayrı çağrılır.
    """
    try:
        clean_symbol          = normalize_symbol(sembol)
        clean_symbol, df, _   = get_stock(clean_symbol)

        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"{clean_symbol} için veri alınamadı.")

        df_analiz, fib_20, fib_200 = teknik_analiz(df)

        if df_analiz.empty:
            raise HTTPException(status_code=400, detail="Teknik analiz için yeterli geçmiş veri yok.")

        son_satir  = df_analiz.iloc[-1]
        sonuc_dl   = dl_bot.analiz_et(df_analiz)
        son_fiyat  = float(son_satir["Close"])

        return {
            "sembol":  clean_symbol.replace(".IS", ""),
            "fiyat":   son_fiyat,
            "tahmin":  round(float(sonuc_dl.get("tahmin", son_fiyat)), 2),
            "guven":   int(sonuc_dl.get("güven", 0)),
            "yon":     sonuc_dl.get("yön", "Nötr"),
            "rsi":     round(float(son_satir.get("RSI", 50.0)), 1),
            "sbs":     round(float(son_satir.get("SBS", 50.0)), 1),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news/{sembol}")
async def get_news(sembol: str):
    """
    Hisse haberleri — her haber ayrı obje olarak döner.

    DÜZELTME: Eskiden tüm haber metni tek bir string'e kesilip
    tek elemanlı liste dönüyordu. Şimdi get_hisse_haberleri()
    ile her haber ayrı dict olarak frontend'e gidiyor.
    """
    try:
        haberler = get_hisse_haberleri(sembol.upper(), limit=10)

        if not haberler:
            return {"haberler": []}

        return {
            "haberler": [
                {
                    "baslik":    h["baslik"],
                    "kaynak":    h["kaynak"],
                    "saat":      h["tarih"],
                    "link":      h["link"],
                    "sentiment": "notr",
                    "hisse":     h["hisse"],
                }
                for h in haberler
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))