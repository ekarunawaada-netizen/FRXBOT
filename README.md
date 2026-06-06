# FRXBOT: Sistem Trading Kuantitatif AI Tingkat Lanjut

FRXBOT adalah asisten trading kuantitatif dan mesin pengambil keputusan tingkat institusional yang terintegrasi dengan Telegram Bot (Aiogram) dan MetaTrader 5 (MT5). Sistem ini dirancang menggunakan database SQLite lokal berkinerja tinggi untuk mengeksekusi perhitungan analitis yang kompleks—menggabungkan data harga live, korelasi makro, data fundamental, dan wawasan semantik Gemini AI—dalam hitungan milidetik.

---

## 🏛️ Arsitektur Database Quant Dashboard (5 Tabel Utama Lokal)

Mesin utama menyimpan semua parameter lokal dan riwayat status di dalam `data/frxbot_brain.db`.

### Tata Letak Skema Relasional

```
                 ┌──────────────────────────────────────┐
                 │         data/frxbot_brain.db         │
                 └──────────────────┬───────────────────┘
                                    │
       ┌──────────────────┬─────────┼─────────┬──────────────────┐
       │                  │         │         │                  │
┌──────▼───────┐   ┌──────▼───────┐ ┌───────▼───────┐  ┌──────▼───────┐   ┌──────▼───────┐
│pair_optimized│   │market_regimes│ │  market_news  │  │    market    │   │ intermarket  │
│    _rules    │   │   _history   │ │   _calendar   │  │  _sentiment  │   │ _correlation │
└──────────────┘   └──────────────┘ └───────────────┘  └──────────────┘   └──────────────┘
```

1. **`pair_optimized_rules`**
   * **Skema**: `symbol (TEXT)`, `timeframe (TEXT)`, `mode (TEXT)`, `sl_atr_multiplier (REAL)`, `tp_atr_multiplier (REAL)`, `bep_multiplier (REAL)`, `win_rate (REAL)`, `profit_factor (REAL)`, `total_profit (REAL)`, `updated_at (TIMESTAMP)`
   * **Metode Ingest**: Dihitung melalui optimasi Grid-Search multi-objektif secara offline (`tests/train_all_pairs.py`) untuk memaksimalkan Win Rate dan Profit Factor.
   * **Batasan**: Dikelola melalui indeks unik pada `(symbol, mode)` untuk mendukung proses pembaruan (upsert) yang bersih.

2. **`market_regimes_history`**
   * **Skema**: `id (INTEGER PRIMARY KEY AUTOINCREMENT)`, `symbol (TEXT)`, `calculated_atr (REAL)`, `standard_deviation (REAL)`, `market_state (TEXT)`, `timestamp (TIMESTAMP)`
   * **Metode Ingest**: Dihitung oleh `core/regime_detector.py` dengan menganalisis rasio ATR jangka pendek/panjang (ATR_14/ATR_100) dan jarak harga penutupan dari saluran EMA_50.
   * **Status**: Mengklasifikasikan kondisi pasar menjadi `HIGH_VOLATILITY`, `TRENDING`, atau `NORMAL`.

3. **`market_news_calendar`**
   * **Skema**: `id (INTEGER PRIMARY KEY AUTOINCREMENT)`, `currency (TEXT)`, `event_name (TEXT)`, `impact_level (TEXT)`, `event_time (DATETIME)`
   * **Metode Ingest**: Mengambil data rilis berita ekonomi secara langsung dari feed XML Forex Factory via `core/news_fetcher.py`.
   * **Batasan**: Batasan unik pada `(currency, event_name, event_time)` untuk pencegahan duplikasi data secara mutlak.

4. **`market_sentiment`**
   * **Skema**: `symbol (TEXT PRIMARY KEY)`, `long_percentage (REAL)`, `short_percentage (REAL)`, `updated_at (DATETIME)`
   * **Metode Ingest**: Memantau metrik posisi klien dengan menarik endpoint publik DailyFX via `core/alternative_data_fetcher.py`. Dilengkapi algoritma fallback dinamis berbasis aksi harga (price action) jika koneksi luar terputus.

5. **`intermarket_correlation`**
   * **Skema**: `ticker (TEXT PRIMARY KEY)`, `current_price (REAL)`, `daily_change_percent (REAL)`, `updated_at (DATETIME)`
   * **Metode Ingest**: Melacak harga penutupan dan persentase perubahan harian dari Indeks Dolar AS (`DX-Y.NYB` / `DXY`) dan Imbal Hasil Obligasi AS 10-Tahun (`^TNX` / `US10Y`) via `core/alternative_data_fetcher.py` menggunakan pustaka `yfinance` dengan fallback koneksi HTTP Yahoo secara langsung.

---

## 🔄 Pipa Alur Kerja Eksekusi Terfaktor

Alur eksekusi dipicu dalam hitungan milidetik ketika pengguna memasukkan perintah `/analisa {SYMBOL} {MODE}` di Telegram:

```
┌─────────────────┐      ┌────────────────────┐      ┌───────────────────────────┐
│ Perintah User   │ ───► │ Cek Whitelist      │ ───► │ Tarik Data Parameter DB   │
└─────────────────┘      └────────────────────┘      │ (Multipliers & Volatility)│
                                                     └─────────────┬─────────────┘
                                                                   │
┌─────────────────┐      ┌────────────────────┐      ┌─────────────▼─────────────┐
│ Level SNR &     │ ◄─── │ Evaluasi Teknikal  │ ◄─── │ Ambil Harga Live          │
│ Indikator       │      │ (EMA, RSI, MACD)   │      │ (MT5 / Fallback Yahoo)    │
└───────┬─────────┘      └────────────────────┘      └───────────────────────────┘
        │
        ▼
┌─────────────────┐      ┌────────────────────┐      ┌───────────────────────────┐
│ Penyandingan    │ ───► │ Analisis Kognitif  │ ───► │ Kalkulasi Risiko Lanjut   │
│ Data Alternatif │      │ AI Gemini          │      │ (Lot Dinamis & Cek Pips)  │
└─────────────────┘      └────────────────────┘      └─────────────┬─────────────┘
                                                                   │
                                                                   ▼
                                                     ┌───────────────────────────┐
                                                     │ Tampilan Dashboard HTML   │
                                                     │ Premium di Telegram       │
                                                     └───────────────────────────┘
```

---

## 💻 Panduan Penerapan Lokal End-to-End di Windows

### Prasyarat
* **Sistem Operasi**: Wajib Windows OS (karena dependensi pustaka `MetaTrader5` yang memerlukan terminal desktop MT5)
* **Python**: Python 3.10 ke atas
* **Platform**: Terminal MetaTrader 5 aktif dan berjalan di host lokal

### Urutan Instalasi (Windows PowerShell)

1. **Kloning Repositori & Masuk ke Workspace**
   ```powershell
   git clone https://github.com/yourusername/ai_forex.git
   cd ai_forex
   ```

2. **Inisialisasi Virtual Environment & Instal Dependensi**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. **Konfigurasi Variabel Lingkungan**
   Buat file bernama `.env` pada direktori root proyek:
   ```env
   TELEGRAM_BOT_TOKEN="token_bot_telegram_anda"
   GEMINI_API_KEY="kunci_api_gemini_anda"
   ADMIN_IDS="6827317690,8147608485"
   DEFAULT_CAPITAL_USD=5000.0
   DEFAULT_RISK_PCT=1.0
   ```

4. **Inisialisasi Database Utama & Seeding Data Awal**
   ```powershell
   python core/database_manager.py
   python data/cloud_data_scraper.py
   ```

5. **Jalankan Saluran Ingest Data Alternatif (Makro & Kalender Berita)**
   ```powershell
   python core/news_fetcher.py
   python core/alternative_data_fetcher.py
   ```

6. **Mulai Layanan Bot Telegram Utama**
   ```powershell
   python main.py
   ```

---

## 💬 Antarmuka Telegram & Kebijakan Aset

### Kumpulan Perintah
* `/start`: Menginisialisasi bot dan memverifikasi otorisasi admin lokal.
* `/help`: Menampilkan panduan cepat penggunaan bot secara lengkap.
* `/analisa {SYMBOL} {MODE}`: Meminta analisis kuantitatif terintegrasi.
  * **Simbol yang Didukung**: `XAUUSD`, `EURUSD`, `GBPUSD`, `USDJPY`, `AUDUSD`, `USDCAD`, `USDCHF`
  * **Mode yang Didukung**: 
    * `scalping`: Profil eksekusi jangka pendek (M5).
    * `intraday`: Profil eksekusi jangka menengah (M30).
    * `swing`: Profil eksekusi jangka panjang (H1 - Default).
  * **Contoh Penggunaan**: `/analisa XAUUSD intraday`
