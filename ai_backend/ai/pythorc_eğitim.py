import warnings
import yfinance as yf
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

warnings.filterwarnings("ignore")
bist_30=["AKBNK.IS", "ALARK.IS", "ARCLK.IS", "ASELS.IS", "ASTOR.IS", 
    "BIMAS.IS", "BRSAN.IS", "CCOLA.IS", "EKGYO.IS", "ENKAI.IS", 
    "EREGL.IS", "FROTO.IS", "GARAN.IS", "GUBRF.IS", "HEKTS.IS", 
    "ISCTR.IS", "KCHOL.IS", "KONTR.IS", "KRDMD.IS", "OYAKC.IS", 
    "PETKM.IS", "PGSUS.IS", "SAHOL.IS", "SASA.IS", "SISE.IS", 
    "TCELL.IS", "THYAO.IS", "TOASO.IS", "TUPRS.IS", "YKBNK.IS"]


class deeplearning:
    """
    İsim aynı kaldı (deeplearning) ki pythorc.py ve backtest_engine.py
    tarafında import isimlerini kırmayalım. İçerik artık RandomForest.
    """

    # 2. VERİ HAZIRLAMA (Cevap Anahtarını Oluşturma) — torch sürümüyle birebir aynı mantık
    @staticmethod
    def verileri_hazirla(symbol_listesi):
        tum_x = []
        tum_y = []

        for symbol in symbol_listesi:
            print(f"{symbol} verileri çekiliyor ve teknik altyapı hazırlanıyor...")

            try:
                df = yf.download(symbol, period="730d", interval="1h", progress=False, multi_level_index=False)

                df['Getiri'] = df['Close'].pct_change()
                df['Hacim_degisimi'] = df['Volume'].pct_change()

                exp1 = df['Close'].ewm(span=12, adjust=False).mean()
                exp2 = df['Close'].ewm(span=26, adjust=False).mean()
                df['MACD'] = exp1 - exp2

                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).ewm(com=13, adjust=False).mean()
                lose = (-delta.where(delta < 0, 0)).ewm(com=13, adjust=False).mean()
                df['RSI'] = 100 - (100 / (1 + (gain / lose)))

                df['SMA_20'] = df['Close'].rolling(window=20).mean()
                df['STD_20'] = df['Close'].rolling(window=20).std()
                df['Bollinger_Upper'] = df['SMA_20'] + (df['STD_20'] * 2)
                df['Bollinger_Lower'] = df['SMA_20'] - (df['STD_20'] * 2)
                df['Bollinger_Konum'] = (df['Close'] - df['Bollinger_Lower']) / (df['Bollinger_Upper'] - df['Bollinger_Lower'])

                df['Momentum'] = df['Close'] / df['Close'].shift(10)

                df['Target'] = df['Close'].shift(-1)

                df.replace([np.inf, -np.inf], np.nan, inplace=True)

                features = ['Close', 'RSI', 'MACD', 'Bollinger_Konum', 'Hacim_degisimi', 'Momentum']
                df_clean = df.dropna(subset=features + ['Target'])

                tum_x.append(df_clean[features].values)
                tum_y.append(df_clean[['Target']].values)

            except Exception as e:
                print(f"Veri çekme hatası: {e}")

        x_dev_matris = np.vstack(tum_x)
        y_dev_matris = np.vstack(tum_y)

        return x_dev_matris, y_dev_matris


if __name__ == "__main__":
    x_raw, y_raw = deeplearning.verileri_hazirla(bist_30)

    # Scaler'ları yine tutuyoruz (tutarlılık kararı) ama RandomForest için
    # X tarafında scale şart değil; yine de inference kodunu birebir koruyalım diye
    # x_scaler'ı da fit ediyoruz, kullanmasak da dosya olarak üretelim.
    x_sacler = MinMaxScaler()
    y_sacler = MinMaxScaler()

    x_scaled = x_sacler.fit_transform(x_raw)
    y_scaled = y_sacler.fit_transform(y_raw)

    # RandomForest ham (unscaled) veriyle de çalışabilir, scaled veriyle de —
    # fark etmez çünkü tree split'leri monotonic transform'lardan etkilenmez.
    # Pipeline tutarlılığı için scaled veri üzerinden eğitiyoruz.
    X_train, X_val, y_train, y_val = train_test_split(
        x_scaled, y_scaled.ravel(), test_size=0.2, shuffle=False
    )

    print(f"\nEğitim seti: {len(X_train)} satır | Doğrulama seti: {len(X_val)} satır\n")

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=5,
        n_jobs=-1,
        random_state=42,
    )

    print("RandomForest eğitiliyor...")
    model.fit(X_train, y_train)

    val_pred = model.predict(X_val)
    mae = mean_absolute_error(y_val, val_pred)
    r2 = r2_score(y_val, val_pred)

    print(f"\nDoğrulama MAE (scaled): {mae:.6f}")
    print(f"Doğrulama R²: {r2:.4f}")

    # Özellik önemlerini de gösterelim, RandomForest'ın bonusu
    features = ['Close', 'RSI', 'MACD', 'Bollinger_Konum', 'Hacim_degisimi', 'Momentum']
    print("\nÖzellik önemleri:")
    for f, imp in sorted(zip(features, model.feature_importances_), key=lambda x: -x[1]):
        print(f"  {f:<18} {imp:.4f}")

    # 1. Modeli kaydet
    joblib.dump(model, "kahin_model.joblib")

    # 2. Ölçekleyicileri kaydet (eskisiyle aynı dosya isimleri — web tarafı bozulmasın)
    joblib.dump(x_sacler, "x_scaler.gz")
    joblib.dump(y_sacler, "y_scaler.gz")

    print("---")
    print("✅ İşlem Başarılı!")
    print("1. 'kahin_model.joblib' (Modelin Beyni — RandomForest)")
    print("2. 'x_scaler.gz' (Girdi Sözlüğü)")
    print("3. 'y_scaler.gz' (Çıktı Sözlüğü)")
    print("Dosyalar klasöre kazındı. Artık web tarafına geçmeye hazırız.")