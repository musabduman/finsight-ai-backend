# main.py — FinSight AI Backend (tek servis)
#
# Eskiden ai_server.py (analiz/chat/haber) ve db_server.py (auth/watchlist)
# iki ayrı Render Web Service olarak deploy ediliyordu. Render free tier'da
# bu, iki ayrı cold-start ve iki ayrı config demekti; ayrıca frontend'de
# 404'lere yol açtı çünkü sadece biri deploy edilmişti.
#
# Artık tek FastAPI app, tek Render servisi, tek URL. Route'lar mantıksal
# olarak routers/auth.py ve routers/analysis.py altında ayrı duruyor —
# kod karışmıyor, ama deploy tarafı basitleşti.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from db import init_db
from routers import auth, analysis

app = FastAPI(title="FinSight AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(analysis.router)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    """Render'da uyku moduna geçmeyi geciktirmek için bir uptime robotuyla
    (örn. cron-job.org) periyodik pinglenebilir."""
    return {"status": "ok"}