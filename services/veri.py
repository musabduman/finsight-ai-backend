"""
FinSight AI — data_fetcher.py
BIST hisse verisi çekme modülü.
"""

import time
import requests
import pandas as pd
import yfinance as yf


# ---------------------------
# SESSION (stabil bağlantı)
# ---------------------------
_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0"})


# ---------------------------
# SYMBOL NORMALIZE
# ---------------------------
def normalize_symbol(symbol: str) -> str:
    """THYAO → THYAO.IS, thyao → THYAO.IS"""
    tr_to_en = str.maketrans("ıiğüşöçIİĞÜŞÖÇ", "IIGUSOCIIGUSOC")
    clean = str(symbol).translate(tr_to_en).upper().strip()
    if not clean.endswith(".IS"):
        clean += ".IS"
    return clean


# ---------------------------
# MULTIINDEX DÜZLEŞTIR
# ---------------------------
def _flatten(df: pd.DataFrame, symbol: str = None) -> pd.DataFrame:
    """
    yfinance bazen MultiIndex döndürür (özellikle tek sembol bulk çekimde).
    Bu fonksiyon her durumda düz DataFrame döner.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        lvl0 = df.columns.get_level_values(0)
        lvl1 = df.columns.get_level_values(1)

        if symbol and symbol in lvl0:
            df = df[symbol]
        elif symbol and symbol in lvl1:
            df = df.xs(symbol, axis=1, level=1)
        else:
            # Sembol bulunamadıysa sadece level-0 isimlerini kullan
            df.columns = lvl0

    df = df.dropna(how="all")
    return df


# ---------------------------
# PRICE DATA  (tekli sembol)
# ---------------------------
def get_price_data(symbol: str) -> pd.DataFrame:
    """
    3 yıllık OHLCV verisi çeker. Hata durumunda 3 kez retry yapar.
    Başarısız olursa boş DataFrame döner.
    """
    for attempt in range(3):
        try:
            df = yf.download(
                symbol,
                period="3y",
                progress=False,
                auto_adjust=True,
                session=_session,
            )
            df = _flatten(df, symbol)

            if not df.empty and "Close" in df.columns:
                return df

        except Exception as e:
            print(f"get_price_data hata (deneme {attempt + 1}/3) [{symbol}]: {e}")
            time.sleep(2 ** attempt)   # 1s, 2s, 4s

    return pd.DataFrame()


# ---------------------------
# FAST INFO
# ---------------------------
def get_fast_info(symbol: str) -> dict:
    """
    Fiyat, piyasa değeri, 52H yüksek/düşük vb. hızlı bilgiler.
    Her zaman dict döner; hata durumunda boş dict.
    """
    try:
        fi = yf.Ticker(symbol, session=_session).fast_info
        return {
            "last_price":              fi.last_price,
            "market_cap":              fi.market_cap,
            "year_high":               fi.year_high,
            "year_low":                fi.year_low,
            "fifty_day_average":       fi.fifty_day_average,
            "two_hundred_day_average": fi.two_hundred_day_average,
            "previous_close":          fi.previous_close,
            "shares":                  fi.shares,
        }
    except Exception as e:
        print(f"get_fast_info hata [{symbol}]: {e}")
        return {}


# ---------------------------
# MAIN STOCK FETCH  (tekli)
# ---------------------------
def get_stock(symbol: str) -> tuple:
    """
    Ana veri çekme fonksiyonu.
    Dönüş: (clean_symbol, df | None, info_dict | None)
    """
    clean = normalize_symbol(symbol)
    try:
        df   = get_price_data(clean)
        info = get_fast_info(clean)

        if df.empty or "Close" not in df.columns:
            print(f"get_stock: {clean} için geçerli fiyat verisi yok")
            return clean, None, None

        return clean, df, info

    except Exception as e:
        print(f"get_stock hata [{clean}]: {e}")
        return clean, None, None


# Alias — app.py ve watchlist.py uyumluluğu
get_stock_data = get_stock


# ---------------------------
# BULK STOCK FETCH  (çoklu)
# ---------------------------
def get_bulk_stocks(symbols: list) -> dict | None:
    """
    Birden fazla sembolü tek API çağrısıyla çeker.
    Dönüş: {clean_symbol: df} dict  |  None (başarısız)

    NOT: yfinance group_by="ticker" ile sembol her zaman
         MultiIndex'in level-0'ında olur.
    """
    if not symbols:
        return None

    clean_symbols = [normalize_symbol(s) for s in symbols]
    symbols_str   = " ".join(clean_symbols)

    try:
        raw = yf.download(
            symbols_str,
            period="3y",
            progress=False,
            auto_adjust=True,
            group_by="ticker",
            session=_session,
        )

        if raw is None or raw.empty:
            print("get_bulk_stocks: ham veri boş geldi")
            return None

        result = {}

        for clean in clean_symbols:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    lvl0 = raw.columns.get_level_values(0)
                    if clean in lvl0:
                        df = raw[clean].copy()
                    else:
                        print(f"bulk: {clean} MultiIndex level-0'da bulunamadı")
                        continue
                else:
                    # Tek sembol geldiğinde MultiIndex olmayabilir
                    df = raw.copy()

                df = _flatten(df, clean)

                if not df.empty and "Close" in df.columns:
                    result[clean] = df
                else:
                    print(f"bulk: {clean} için Close kolonu yok, atlandı")

            except Exception as e:
                print(f"bulk parse hata [{clean}]: {e}")
                continue

        return result if result else None

    except Exception as e:
        print(f"get_bulk_stocks hata: {e}")
        return None


# ---------------------------
# FUNDAMENTAL HESAPLA
# ---------------------------
def get_temel_hesapla(symbol: str) -> dict:
    """
    FK, PD/DD, Piyasa Değeri hesaplar.
    BIST'te yfinance fundamentals güvenilmez olabilir;
    her değer için fallback "Yok" döner.
    """
    ticker    = yf.Ticker(normalize_symbol(symbol), session=_session)
    sonuc     = {}
    piyasa_degeri = None

    # --- Piyasa Değeri & 52H ---
    try:
        fast          = ticker.fast_info
        piyasa_degeri = fast.market_cap

        sonuc["Piyasa Değeri"] = f"{piyasa_degeri / 1e9:.2f}B ₺"
        sonuc["52H Yüksek"]   = round(fast.year_high, 2)
        sonuc["52H Düşük"]    = round(fast.year_low,  2)
    except Exception as e:
        print(f"fast_info hata [{symbol}]: {e}")
        sonuc.setdefault("Piyasa Değeri", "Yok")
        sonuc.setdefault("52H Yüksek",    "Yok")
        sonuc.setdefault("52H Düşük",     "Yok")

    # --- FK (Fiyat/Kazanç) ---
    try:
        income  = ticker.financials
        net_kar = None

        for aday in [
            "Net Income",
            "Net Income Continuous Operations",
            "Net Income Common Stockholders",
        ]:
            if aday in income.index:
                net_kar = income.loc[aday].iloc[0]
                break

        if net_kar is not None and piyasa_degeri:
            if net_kar > 0:
                sonuc["FK"] = round(piyasa_degeri / net_kar, 2)
            else:
                sonuc["FK"] = "Zararda"
        else:
            sonuc["FK"] = "Yok"

    except Exception as e:
        print(f"FK hata [{symbol}]: {e}")
        sonuc["FK"] = "Yok"

    # --- PD/DD (Piyasa Değeri / Defter Değeri) ---
    try:
        balance  = ticker.balance_sheet
        ozkaynak = None

        for aday in [
            "Stockholders Equity",
            "Total Equity Gross Minority Interest",
            "Common Stock Equity",
        ]:
            if aday in balance.index:
                ozkaynak = balance.loc[aday].iloc[0]
                break

        if ozkaynak is not None and piyasa_degeri:
            if ozkaynak > 0:
                sonuc["PD/DD"] = round(piyasa_degeri / ozkaynak, 2)
            else:
                sonuc["PD/DD"] = "Negatif Özkaynak"
        else:
            sonuc["PD/DD"] = "Yok"

    except Exception as e:
        print(f"PD/DD hata [{symbol}]: {e}")
        sonuc["PD/DD"] = "Yok"

    return sonuc