# config.py — FinSight AI ortak ayarlar

import os

# Prod frontend adresi. Sonunda "/" OLMAMALI — tarayıcı Origin header'ı
# asla path ile gelmez, sadece scheme+host+port gönderir.
FRONTEND_URL = "https://finsight-ai-frontend-gules.vercel.app"

# Local geliştirme yaparken frontend'i localhost'ta çalıştırıyorsan
# ENV=dev ortam değişkenini ayarla, otomatik localhost origin'leri de eklenir.
_env = os.getenv("ENV", "production")

CORS_ORIGINS = [FRONTEND_URL]

if _env == "dev":
    CORS_ORIGINS += [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ]