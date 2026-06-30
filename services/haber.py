"""
FinSight AI — news_fetcher.py
BİST hisse haberleri için RSS tabanlı haber çekme modülü.
Kaynak: Google News RSS (sembol bazlı arama) + Investing.com genel feed
"""

import ssl
import urllib.request
import feedparser

from datetime import datetime
from urllib.error import URLError


# ---------------------------
# SSL HANDLER  (sadece feedparser için)
# ---------------------------
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode    = ssl.CERT_NONE

_https_handler = urllib.request.HTTPSHandler(context=_ssl_ctx)
_opener        = urllib.request.build_opener(_https_handler)


def _safe_parse(url: str) -> feedparser.FeedParserDict:
    """SSL sorunlarına karşı güvenli feedparser çağrısı."""
    try:
        response = _opener.open(url, timeout=8)
        return feedparser.parse(response)
    except URLError as e:
        print(f"RSS bağlantı hatası [{url}]: {e}")
        return feedparser.FeedParserDict(entries=[])
    except Exception as e:
        print(f"RSS parse hatası [{url}]: {e}")
        return feedparser.FeedParserDict(entries=[])


def _parse_date(entry) -> str:
    """RSS entry'den gerçek yayın tarihini çeker."""
    if entry.get("published_parsed"):
        try:
            dt = datetime(*entry["published_parsed"][:6])
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _clean_summary(title: str, description: str) -> str:
    """Başlık ve açıklama tekrarını önler."""
    if not description or description.strip() == title.strip():
        return title
    # Bazı RSS'lerde description HTML içeriyor, sadece ilk 200 karakter al
    desc = description[:200].strip()
    return f"{title} — {desc}"


# ---------------------------
# GENEL BİST HABERLERİ
# ---------------------------
GENEL_RSS = {
    "Investing BİST":       "https://tr.investing.com/rss/news_301.rss",
    "Investing Şirketler":  "https://tr.investing.com/rss/news_437.rss",
    "Investing Son Dakika":  "https://tr.investing.com/rss/news_285.rss",
    "Investing Ekonomi":    "https://tr.investing.com/rss/news_14.rss",
}


def get_genel_haberler(limit_per_source: int = 5) -> list[dict]:
    """
    Genel BİST ve ekonomi haberlerini çeker.
    Dönüş: haber dict listesi
    """
    haberler = []

    for kaynak_adi, rss_url in GENEL_RSS.items():
        feed = _safe_parse(rss_url)

        for entry in feed.entries[:limit_per_source]:
            baslik = entry.get("title", "").strip()
            ozet   = _clean_summary(baslik, entry.get("description", ""))

            haberler.append({
                "hisse":  "BİST Genel",
                "baslik": baslik,
                "ozet":   ozet,
                "duygu":  "Nötr",
                "kaynak": kaynak_adi,
                "link":   entry.get("link", ""),
                "tarih":  _parse_date(entry),
            })

    return haberler


# ---------------------------
# HİSSE BAZLI HABERLER  (Google News)
# ---------------------------
def get_hisse_haberleri(sembol: str, limit: int = 10) -> list[dict]:
    """
    Belirli bir hisse için Google News RSS üzerinden haber çeker.
    THYAO.IS veya THYAO her ikisi de kabul edilir.

    Google News birden fazla Türkçe kaynağı (Ekonomim, BloombergHT,
    Dünya, Borsa Gündem vb.) tek sorguda toplar.
    """
    temiz = sembol.replace(".IS", "").upper().strip()

    # İki sorgu: kısa kod + "hisse" kelimesi ile
    sorgular = [
        f"{temiz} hisse borsa",
        f"{temiz} BİST",
    ]

    haberler = []
    gorulmus = set()   # Başlık bazlı duplicate önleme

    for sorgu in sorgular:
        url  = f"https://news.google.com/rss/search?q={sorgu}&hl=tr&gl=TR&ceid=TR:tr"
        feed = _safe_parse(url)

        for entry in feed.entries[:limit]:
            baslik = entry.get("title", "").strip()

            if not baslik or baslik in gorulmus:
                continue

            gorulmus.add(baslik)
            ozet = _clean_summary(baslik, entry.get("description", ""))

            haberler.append({
                "hisse":  temiz,
                "baslik": baslik,
                "ozet":   ozet,
                "duygu":  "Nötr",
                "kaynak": entry.get("source", {}).get("title", "Google News"),
                "link":   entry.get("link", ""),
                "tarih":  _parse_date(entry),
            })

        if len(haberler) >= limit:
            break

    return haberler[:limit]


# ---------------------------
# METIN ÇIKTI  (AI entegrasyonu için)
# ---------------------------
def anlik_hisse_haberi_cek(sembol: str, limit: int = 5) -> str:
    """
    Belirli bir hisse için anlık haberleri metin olarak döner.
    LLM prompt'una doğrudan gömülebilir format.
    """
    haberler = get_hisse_haberleri(sembol, limit=limit)

    if not haberler:
        return f"{sembol} için haber bulunamadı."

    satirlar = []
    for h in haberler:
        satirlar.append(f"[{h['tarih']}] [{h['kaynak']}] {h['ozet']}")

    return "\n".join(satirlar)


# ---------------------------
# TEST
# ---------------------------
if __name__ == "__main__":
    print("=== THYAO Haberleri ===")
    print(anlik_hisse_haberi_cek("THYAO", limit=5))

    print("\n=== Genel BİST (ilk 3) ===")
    genel = get_genel_haberler(limit_per_source=3)
    for h in genel[:5]:
        print(f"[{h['tarih']}] [{h['kaynak']}] {h['baslik']}")