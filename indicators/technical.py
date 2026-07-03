"""
FinSight AI — data_fetcher.py
BIST hisse verisi çekme modülü (İş Yatırım API + Kısmi yfinance)
"""

import time
import requests
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf

# ---------------------------
# SESSION (stabil bağlantı)
# ---------------------------
_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})

# ---------------------------
# SYMBOL NORMALIZE
# ---------------------------
def normalize_symbol(symbol: str, for_isyatirim: bool = False) -> str:
    """
    for_isyatirim=True ise 'GARAN' döner.
    for_isyatirim=False ise 'GARAN.IS' döner.
    """
    tr_to_en = str.maketrans("ıiğüşöçIİĞÜŞÖÇ", "IIGUSOCIIGUSOC")
    clean = str(symbol).translate(tr_to_en).upper().strip()
    
    if for_isyatirim:
        return clean.replace(".IS", "")
    else:
        if not clean.endswith(".IS"):
            clean += ".IS"
        return clean

# ---------------------------
# PRICE DATA  (İş Yatırım - Limitsiz)
# ---------------------------
def get_price_data(symbol: str) -> pd.DataFrame:
    """
    İş Yatırım API üzerinden 3 yıllık OHLCV verisi çeker.
    Hata durumunda 3 kez retry yapar.
    """
    clean_is = normalize_symbol(symbol, for_isyatirim=True)
    bugun = datetime.now().strftime("%d-%m-%Y")
    # 3 yıllık veri için:
    bir_yil_once = (datetime.now() - timedelta(days=365*3)).strftime("%d-%m-%Y")

    url = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/HisseTekil"
    params = {
        "hisse": clean_is,
        "startdate": bir_yil_once,
        "enddate": bugun,
        "period": "1440" # Günlük veri
    }

    for attempt in range(3):
        try:
            res = _session.get(url, params=params, timeout=10)
            data = res.json()
            
            if 'value' in data and data['value']:
                df = pd.DataFrame(data['value'])
                # Sütunları yfinance standardına çevir
                df = df[['HGDG_TARIH', 'HGDG_ACILIS', 'HGDG_YUKSEK', 'HGDG_DUSUK', 'HGDG_KAPANIS', 'HGDG_HACIM']]
                df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
                
                df['Date'] = pd.to_datetime(df['Date'], format='%d-%m-%Y')
                df.set_index('Date', inplace=True)
                df = df.astype(float)
                
                return df
        except Exception as e:
            print(f"get_price_data hata (deneme {attempt + 1}/3) [{clean_is}]: {e}")
            time.sleep(1)

    return pd.DataFrame()

# ---------------------------
# FAST INFO (DataFrame üzerinden manuel hesaplama)
# ---------------------------
def get_fast_info(df: pd.DataFrame) -> dict:
    """
    API'ye istek atmadan, eldeki DataFrame üzerinden istatistikleri çıkarır.
    """
    if df.empty:
        return {}
        
    try:
        last_price = float(df['Close'].iloc[-1])
        prev_close = float(df['Close'].iloc[-2]) if len(df) > 1 else last_price
        
        # Son 1 yıl (yaklaşık 252 işlem günü)
        year_data = df.tail(252)
        
        return {
            "last_price": last_price,
            "market_cap": "Bilinmiyor", # İş yatırım grafiğinden piyasa değeri çıkmaz
            "year_high": float(year_data['High'].max()),
            "year_low": float(year_data['Low'].min()),
            "fifty_day_average": float(df['Close'].tail(50).mean()) if len(df) >= 50 else last_price,
            "two_hundred_day_average": float(df['Close'].tail(200).mean()) if len(df) >= 200 else last_price,
            "previous_close": prev_close,
            "shares": "Bilinmiyor",
        }
    except Exception as e:
        print(f"get_fast_info hesaplama hatası: {e}")
        return {}

# ---------------------------
# MAIN STOCK FETCH  (tekli)
# ---------------------------
def get_stock(symbol: str) -> tuple:
    clean = normalize_symbol(symbol, for_isyatirim=False) # Frontend .IS bekler
    df = get_price_data(symbol)

    if df.empty:
        print(f"get_stock: {clean} için geçerli fiyat verisi yok")
        return clean, None, None

    info = get_fast_info(df)
    return clean, df, info

get_stock_data = get_stock

# ---------------------------
# BULK STOCK FETCH  (çoklu / tarama)
# ---------------------------
def get_bulk_stocks(symbols: list) -> dict | None:
    """
    BIST30 veya Mega Tarama için İş Yatırım'dan sırayla veri çeker.
    """
    if not symbols:
        return None

    result = {}
    for sym in symbols:
        df = get_price_data(sym)
        if not df.empty:
            clean = normalize_symbol(sym, for_isyatirim=False)
            result[clean] = df
        
        # Sunucuyu bir anda boğmamak için minik bir nefes (Ban yememek için)
        time.sleep(0.1) 

    return result if result else None

# ---------------------------
# FUNDAMENTAL HESAPLA (Sadece bu yfinance kullanır)
# ---------------------------
def get_temel_hesapla(symbol: str) -> dict:
    """
    FK, PD/DD hesaplamaları için yfinance kullanırız. 
    Bu işlem nadir yapıldığı için rate limit riski düşüktür.
    """
    clean_yf = normalize_symbol(symbol, for_isyatirim=False)
    ticker = yf.Ticker(clean_yf, session=_session)
    sonuc = {}
    piyasa_degeri = None

    try:
        fast = ticker.fast_info
        piyasa_degeri = fast.market_cap
        sonuc["Piyasa Değeri"] = f"{piyasa_degeri / 1e9:.2f}B ₺"
        sonuc["52H Yüksek"]   = round(fast.year_high, 2)
        sonuc["52H Düşük"]    = round(fast.year_low,  2)
    except Exception as e:
        sonuc.setdefault("Piyasa Değeri", "Yok")
        sonuc.setdefault("52H Yüksek",    "Yok")
        sonuc.setdefault("52H Düşük",     "Yok")

    try:
        income = ticker.financials
        net_kar = None
        for aday in ["Net Income", "Net Income Continuous Operations", "Net Income Common Stockholders"]:
            if aday in income.index:
                net_kar = income.loc[aday].iloc[0]
                break

        if net_kar is not None and piyasa_degeri:
            sonuc["FK"] = round(piyasa_degeri / net_kar, 2) if net_kar > 0 else "Zararda"
        else:
            sonuc["FK"] = "Yok"
    except Exception:
        sonuc["FK"] = "Yok"

    try:
        balance = ticker.balance_sheet
        ozkaynak = None
        for aday in ["Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"]:
            if aday in balance.index:
                ozkaynak = balance.loc[aday].iloc[0]
                break

        if ozkaynak is not None and piyasa_degeri:
            sonuc["PD/DD"] = round(piyasa_degeri / ozkaynak, 2) if ozkaynak > 0 else "Negatif Özkaynak"
        else:
            sonuc["PD/DD"] = "Yok"
    except Exception:
        sonuc["PD/DD"] = "Yok"

    return sonuc