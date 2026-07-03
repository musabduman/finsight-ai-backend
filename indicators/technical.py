import requests
import pandas as pd
from datetime import datetime, timedelta

def get_hisse_data(sembol):
    try:
        # BIST sembollerindeki .IS takısını temizliyoruz (Örn: GARAN.IS -> GARAN)
        temiz_sembol = sembol.replace(".IS", "")
        
        # İş Yatırım tarihi GG-AA-YYYY formatında ister
        bugun = datetime.now().strftime("%d-%m-%Y")
        bir_yil_once = (datetime.now() - timedelta(days=365)).strftime("%d-%m-%Y")

        url = f"https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/HisseTekil"
        params = {
            "hisse": temiz_sembol,
            "startdate": bir_yil_once,
            "enddate": bugun,
            "period": "1440" # Günlük veri
        }

        # İsteği atıyoruz, User-Agent eklemek her zaman iyidir
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, params=params, headers=headers)
        data = response.json()

        if 'value' in data and data['value']:
            df = pd.DataFrame(data['value'])
            
            # Sütunları yfinance ile birebir aynı isimlere çeviriyoruz ki alttaki RSI/MACD kodların çökmesin
            df = df[['HGDG_TARIH', 'HGDG_ACILIS', 'HGDG_YUKSEK', 'HGDG_DUSUK', 'HGDG_KAPANIS', 'HGDG_HACIM']]
            df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']

            # Tarih formatını ayarla ve Index yap
            df['Date'] = pd.to_datetime(df['Date'], format='%d-%m-%Y')
            df.set_index('Date', inplace=True)

            # Sütunları sayısal formata çevir
            df = df.astype(float)
            
            return df
        else:
            print(f"{sembol} için veri bulunamadı.")
            return pd.DataFrame()

    except Exception as e:
        print(f"İş Yatırım veri çekme hatası ({sembol}): {e}")
        return pd.DataFrame()