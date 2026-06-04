const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, LevelFormat, ExternalHyperlink,
  TabStopType, TabStopPosition, PageBreak
} = require('docx');
const fs = require('fs');

// ─── COLOR PALETTE ───────────────────────────────────────────────────────────
const C = {
  darkBlue: '0D1B2A',
  midBlue:  '1B4F72',
  accent:   '2E86C1',
  gold:     'F39C12',
  green:    '27AE60',
  red:      'C0392B',
  lightBg:  'EAF4FB',
  altRow:   'F2F9FF',
  white:    'FFFFFF',
  gray:     '7F8C8D',
  lightGray:'ECF0F1',
  border:   'AED6F1',
  codeBg:   '1E2B37',
  codeText: 'A8D8EA',
  orange:   'E67E22',
};

// ─── HELPERS ─────────────────────────────────────────────────────────────────
const b  = { style: BorderStyle.SINGLE, size: 1, color: C.border };
const nb = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
const borders = { top: b, bottom: b, left: b, right: b };
const noBorders = { top: nb, bottom: nb, left: nb, right: nb };

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 400, after: 160 },
    children: [new TextRun({ text, bold: true, font: 'Arial', size: 32, color: C.darkBlue })],
    border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: C.accent, space: 1 } },
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 120 },
    children: [new TextRun({ text, bold: true, font: 'Arial', size: 26, color: C.midBlue })],
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 80 },
    children: [new TextRun({ text, bold: true, font: 'Arial', size: 22, color: C.accent })],
  });
}

function h4(text) {
  return new Paragraph({
    spacing: { before: 160, after: 60 },
    children: [new TextRun({ text, bold: true, font: 'Arial', size: 20, color: C.gold })],
  });
}

function para(runs, spacing = { before: 80, after: 80 }) {
  const children = Array.isArray(runs)
    ? runs.map(r => new TextRun({ font: 'Arial', size: 20, ...r }))
    : [new TextRun({ text: runs, font: 'Arial', size: 20 })];
  return new Paragraph({ spacing, children });
}

function bullet(text, level = 0) {
  return new Paragraph({
    numbering: { reference: 'bullets', level },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, font: 'Arial', size: 20 })],
  });
}

function numList(text, level = 0) {
  return new Paragraph({
    numbering: { reference: 'numbers', level },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, font: 'Arial', size: 20 })],
  });
}

function codeBlock(lines) {
  return lines.map((line, i) =>
    new Paragraph({
      spacing: { before: i === 0 ? 80 : 0, after: i === lines.length - 1 ? 80 : 0 },
      shading: { fill: C.codeBg, type: ShadingType.CLEAR },
      indent: { left: 360 },
      children: [new TextRun({ text: line, font: 'Courier New', size: 17, color: C.codeText })],
    })
  );
}

function sep() {
  return new Paragraph({
    spacing: { before: 200, after: 200 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: C.lightGray, space: 1 } },
    children: [],
  });
}

function spacer(before = 120) {
  return new Paragraph({ spacing: { before, after: 0 }, children: [] });
}

function cell(content, opts = {}) {
  const {
    fill = C.white, bold = false, color = C.darkBlue, align = AlignmentType.LEFT,
    vAlign = VerticalAlign.CENTER, width = 2000, isHeader = false,
  } = opts;
  const children = Array.isArray(content)
    ? content.map(c => new Paragraph({
        alignment: align,
        children: [new TextRun({ text: c, font: 'Arial', size: isHeader ? 19 : 18, bold: isHeader || bold, color })],
      }))
    : [new Paragraph({
        alignment: align,
        children: [new TextRun({ text: content, font: 'Arial', size: isHeader ? 19 : 18, bold: isHeader || bold, color })],
      })];
  return new TableCell({
    borders,
    shading: { fill, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 100, right: 100 },
    verticalAlign: vAlign,
    width: { size: width, type: WidthType.DXA },
    children,
  });
}

function headerRow(cols, widths) {
  return new TableRow({
    tableHeader: true,
    children: cols.map((c, i) => cell(c, { fill: C.midBlue, color: C.white, bold: true, width: widths[i], isHeader: true })),
  });
}

function dataRow(cols, widths, even = true) {
  return new TableRow({
    children: cols.map((c, i) => cell(c, { fill: even ? C.white : C.altRow, width: widths[i] })),
  });
}

// ─── BADGE / CALLOUT ──────────────────────────────────────────────────────────
function callout(label, text, color = C.accent) {
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    indent: { left: 200 },
    border: { left: { style: BorderStyle.SINGLE, size: 16, color, space: 2 } },
    shading: { fill: C.lightBg, type: ShadingType.CLEAR },
    children: [
      new TextRun({ text: label + '  ', font: 'Arial', size: 19, bold: true, color }),
      new TextRun({ text, font: 'Arial', size: 19, color: C.darkBlue }),
    ],
  });
}

// ─── PAGE BREAK ───────────────────────────────────────────────────────────────
function pageBreak() {
  return new Paragraph({ children: [new TextRun({ break: 1 })] });
}

// ─────────────────────────────────────────────────────────────────────────────
// DOCUMENT CONTENT
// ─────────────────────────────────────────────────────────────────────────────
const children = [];

// ══════════════════════════════════════════════════════════════════════════════
// COVER PAGE
// ══════════════════════════════════════════════════════════════════════════════
children.push(spacer(800));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 0, after: 40 },
  children: [new TextRun({ text: '🤖', font: 'Segoe UI Emoji', size: 80 })],
}));
children.push(spacer(120));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 0, after: 60 },
  children: [new TextRun({ text: 'FOREX AI CO-PILOT', font: 'Arial', size: 56, bold: true, color: C.darkBlue })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 0, after: 40 },
  children: [new TextRun({ text: 'TELEGRAM BOT', font: 'Arial', size: 48, bold: true, color: C.accent })],
}));
children.push(sep());
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 80, after: 20 },
  children: [new TextRun({ text: 'Product Requirements Document  ·  Technical Architecture Design', font: 'Arial', size: 24, color: C.midBlue })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 0, after: 0 },
  children: [new TextRun({ text: 'Version 1.0  ·  June 2025  ·  CONFIDENTIAL — Private Whitelist Project', font: 'Arial', size: 19, color: C.gray, italics: true })],
}));
children.push(spacer(400));

// Cover meta table
children.push(new Table({
  width: { size: 9000, type: WidthType.DXA },
  columnWidths: [2400, 6600],
  rows: [
    new TableRow({ children: [
      cell('Prepared By', { fill: C.darkBlue, color: C.gold, bold: true, width: 2400, isHeader: true }),
      cell('Lead Quant Developer & Senior Product Manager', { fill: C.lightBg, width: 6600 }),
    ]}),
    new TableRow({ children: [
      cell('Classification', { fill: C.darkBlue, color: C.gold, bold: true, width: 2400, isHeader: true }),
      cell('PRIVATE — Whitelist: 2-5 Authorized Users Only', { fill: C.lightBg, width: 6600 }),
    ]}),
    new TableRow({ children: [
      cell('Tech Stack', { fill: C.darkBlue, color: C.gold, bold: true, width: 2400, isHeader: true }),
      cell('Python 3.10+ · aiogram 3.x · Gemini API · PostgreSQL · Docker', { fill: C.lightBg, width: 6600 }),
    ]}),
    new TableRow({ children: [
      cell('Target Deploy', { fill: C.darkBlue, color: C.gold, bold: true, width: 2400, isHeader: true }),
      cell('Linux VPS via Docker Compose (dev: Google Antigravity Cloud IDE)', { fill: C.lightBg, width: 6600 }),
    ]}),
  ],
}));
children.push(pageBreak());

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 1 — EXECUTIVE SUMMARY
// ══════════════════════════════════════════════════════════════════════════════
children.push(h1('1. Executive Summary'));
children.push(para('Forex AI Co-Pilot adalah asisten trading privat berbasis Telegram yang menggabungkan analisis fundamental berbasis AI (Google Gemini), teknikal kuantitatif real-time, manajemen risiko otomatis, dan backtesting vektorisasi dalam satu platform yang sepenuhnya asinkron. Sistem ini dirancang sebagai whitelist-only (2–5 user) untuk menjaga latensi, keamanan, dan biaya API tetap terkendali.'));
children.push(spacer(80));
children.push(callout('Core Value Proposition:', 'Setiap sinyal yang dihasilkan bukan sekadar "Buy/Sell" — melainkan paket keputusan lengkap: Entry Price, Dynamic SL (ATR-based), multiple TP levels (RRR 1:1.5 & 1:2), dan Lot Size recommendation berdasarkan capital exposure, sehingga user hanya perlu klik "Execute" di broker mereka.'));
children.push(spacer(80));

children.push(h2('1.1 Flow Logika Sistem (High-Level)'));

children.push(new Table({
  width: { size: 9000, type: WidthType.DXA },
  columnWidths: [500, 2800, 2900, 2800],
  rows: [
    headerRow(['#', 'Trigger / Input', 'Engine yang Aktif', 'Output ke User'], [500, 2800, 2900, 2800]),
    dataRow(['1', 'Scheduler (tiap 1–4 jam)', 'Fundamental Radar → Gemini AI', 'Push Notif: Sinyal LONG/SHORT + Risk Pack'], [500, 2800, 2900, 2800], true),
    dataRow(['2', '/analisa [PAIR]', 'Technical Analysis Engine', 'On-demand: Chart indikator + Confluence Score'], [500, 2800, 2900, 2800], false),
    dataRow(['3', '/backtest [PAIR] [TF]', 'Vectorbt Backtest + Async Job Queue', 'Report: WinRate, PnL, MaxDD, Total Trades'], [500, 2800, 2900, 2800], true),
    dataRow(['4', '/status, /help', 'Telegram Handler (ringan)', 'Info bot, whitelist check, panduan command'], [500, 2800, 2900, 2800], false),
  ],
}));

children.push(spacer(120));
children.push(h3('Alur Data End-to-End'));
children.push(...codeBlock([
  '  [Scheduler / User Command]',
  '        │',
  '        ▼',
  '  [aiogram Dispatcher]  ──→  [Whitelist Middleware]  ──→  REJECT if not authorized',
  '        │',
  '        ▼',
  '  ┌─────────────────────────────────────────────────────────┐',
  '  │                  HANDLER LAYER (async)                  │',
  '  │  push_handler │ analisa_handler │ backtest_handler       │',
  '  └─────┬─────────────────┬──────────────────┬─────────────┘',
  '        │                 │                  │',
  '        ▼                 ▼                  ▼',
  '  [News Fetcher]   [OHLC Fetcher]    [Job Queue (asyncio)]',
  '  [Gemini AI]      [pandas_ta]       [Worker Process]',
  '  [Risk Engine]    [Risk Engine]     [vectorbt Engine]',
  '        │                 │                  │',
  '        └────────┬────────┘                  │',
  '                 ▼                           │',
  '        [PostgreSQL Logger]  ←───────────────┘',
  '                 │',
  '                 ▼',
  '        [Telegram Message Formatter]  ──→  User Receives Signal',
]));
children.push(pageBreak());

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 2 — SYSTEM ARCHITECTURE
// ══════════════════════════════════════════════════════════════════════════════
children.push(h1('2. System Architecture'));

children.push(h2('2.1 Prinsip Desain Utama'));
children.push(bullet('Fully Asynchronous: Seluruh I/O (HTTP, DB, Telegram) menggunakan async/await — tidak ada blocking call.'));
children.push(bullet('Separation of Concerns: Telegram handler tidak pernah melakukan komputasi berat; handler hanya dispatch job ke queue lalu segera return.'));
children.push(bullet('Backpressure Control: Job queue memiliki kapasitas maksimum untuk mencegah OOM saat banyak request backtest simultan.'));
children.push(bullet('Stateless Handlers: State disimpan di DB/Redis, bukan di memori handler, sehingga restart bot tidak kehilangan data.'));
children.push(bullet('Rate-Limit Aware: Semua API call (price data, Gemini, Telegram) melewati rate-limiter layer sebelum dikirimkan.'));

children.push(spacer(80));
children.push(h2('2.2 Komponen Arsitektur'));

children.push(new Table({
  width: { size: 9000, type: WidthType.DXA },
  columnWidths: [2000, 2500, 2500, 2000],
  rows: [
    headerRow(['Komponen', 'Library/Tool', 'Fungsi', 'Komunikasi'], [2000, 2500, 2500, 2000]),
    dataRow(['Telegram Layer', 'aiogram 3.x', 'Webhook/polling, routing, middleware', 'asyncio event loop'], [2000, 2500, 2500, 2000], true),
    dataRow(['Fundamental Engine', 'httpx, BeautifulSoup4', 'Scrape kalender ekonomi, news feed', 'async HTTP'], [2000, 2500, 2500, 2000], false),
    dataRow(['AI Engine', 'google-generativeai', 'Sentiment analysis, signal direction', 'async REST'], [2000, 2500, 2500, 2000], true),
    dataRow(['Price Data', 'yfinance / CCXT / Alpha Vantage', 'OHLCV candle data (spot & historical)', 'async HTTP + cache'], [2000, 2500, 2500, 2000], false),
    dataRow(['Technical Engine', 'pandas, pandas_ta', 'EMA, RSI, MACD, ATR calculation', 'in-process'], [2000, 2500, 2500, 2000], true),
    dataRow(['Risk Engine', 'numpy, custom module', 'ATR-SL, RRR-TP, lot sizing', 'in-process'], [2000, 2500, 2500, 2000], false),
    dataRow(['Backtest Engine', 'vectorbt (vbt)', 'Vectorized historical simulation', 'asyncio subprocess / ProcessPoolExecutor'], [2000, 2500, 2500, 2000], true),
    dataRow(['Job Queue', 'asyncio.Queue + ProcessPoolExecutor', 'Non-blocking backtest dispatch', 'asyncio IPC'], [2000, 2500, 2500, 2000], false),
    dataRow(['Database', 'PostgreSQL (Supabase) + asyncpg', 'Whitelist, signal log, backtest results', 'async TCP'], [2000, 2500, 2500, 2000], true),
    dataRow(['Cache Layer', 'Redis (opsional) / in-memory TTL', 'OHLCV cache, rate-limit counter', 'async'], [2000, 2500, 2500, 2000], false),
    dataRow(['Containerization', 'Docker + Docker Compose', 'Isolasi layanan, deployment VPS', 'Docker network'], [2000, 2500, 2500, 2000], true),
  ],
}));

children.push(spacer(120));
children.push(h2('2.3 Async Job Queue untuk Backtest'));
children.push(para([
  { text: 'PROBLEM: ', bold: true, color: C.red },
  { text: 'vectorbt dapat memakan memori 200–800 MB dan CPU seconds untuk data 5 tahun. Jika dijalankan langsung di Telegram handler, event loop akan FROZEN — tidak ada user lain yang bisa dilayani. ' },
]));
children.push(spacer(60));
children.push(para([
  { text: 'SOLUTION: ', bold: true, color: C.green },
  { text: 'Gunakan asyncio.Queue + concurrent.futures.ProcessPoolExecutor. Handler cukup submit job, kirim pesan "Backtest sedang diproses...", lalu loop event tetap bebas melayani request lain.' },
]));
children.push(spacer(80));

children.push(...codeBlock([
  '# core/job_queue.py',
  '',
  'import asyncio',
  'from concurrent.futures import ProcessPoolExecutor',
  'from typing import Callable, Any',
  '',
  'class BacktestJobQueue:',
  '    """Non-blocking job queue untuk heavy backtest computation."""',
  '    ',
  '    def __init__(self, max_workers: int = 2, max_queue_size: int = 5):',
  '        self.executor = ProcessPoolExecutor(max_workers=max_workers)',
  '        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)',
  '        self.loop = asyncio.get_event_loop()',
  '    ',
  '    async def submit(self, func: Callable, *args, **kwargs) -> Any:',
  '        """Submit backtest job, returns awaitable result."""',
  '        if self.queue.full():',
  '            raise QueueFullError("Backtest queue penuh. Coba beberapa menit lagi.")',
  '        await self.queue.put(True)  # semaphore token',
  '        try:',
  '            result = await self.loop.run_in_executor(',
  '                self.executor,',
  '                lambda: func(*args, **kwargs)  # runs in subprocess',
  '            )',
  '            return result',
  '        finally:',
  '            self.queue.get_nowait()  # release semaphore',
  '            self.queue.task_done()',
]));

children.push(spacer(80));
children.push(callout('⚠️ RAM Budget:', 'Set max_workers=2 pada VPS 2GB RAM. Satu backtest process vectorbt butuh ~300-500MB. Dengan 2 worker, peak usage ~1GB, sisanya untuk bot + Postgres.'));

children.push(spacer(120));
children.push(h2('2.4 Rate Limiting Strategy'));
children.push(h3('A. Telegram Rate Limit'));
children.push(para('Telegram membatasi: 30 pesan/detik global, 1 pesan/detik per chat. aiogram 3.x memiliki built-in ThrottlingMiddleware, namun perlu dikonfigurasi dengan benar.'));
children.push(spacer(60));
children.push(...codeBlock([
  '# middlewares/rate_limiter.py',
  '',
  'from aiogram import BaseMiddleware',
  'from aiogram.types import Message',
  'from cachetools import TTLCache',
  'import asyncio',
  '',
  'class UserRateLimitMiddleware(BaseMiddleware):',
  '    """Limit per-user: max 3 heavy commands per 60 detik."""',
  '    ',
  '    def __init__(self, rate_limit: int = 3, window: int = 60):',
  '        self.cache = TTLCache(maxsize=500, ttl=window)',
  '        self.rate_limit = rate_limit',
  '    ',
  '    async def __call__(self, handler, event: Message, data: dict):',
  '        user_id = event.from_user.id',
  '        count = self.cache.get(user_id, 0)',
  '        if count >= self.rate_limit:',
  '            await event.answer("⏳ Terlalu banyak request. Tunggu sebentar.")',
  '            return  # drop request',
  '        self.cache[user_id] = count + 1',
  '        return await handler(event, data)',
]));

children.push(spacer(80));
children.push(h3('B. Price Data API Rate Limit'));
children.push(para('API sumber data OHLCV (Alpha Vantage free: 5 req/menit, yfinance: ~2000 req/hari unofficial) harus dijaga dengan kombinasi caching dan exponential backoff.'));
children.push(spacer(60));
children.push(...codeBlock([
  '# core/price_fetcher.py — Cache + Exponential Backoff',
  '',
  'import asyncio, time',
  'from functools import wraps',
  'from cachetools import TTLCache',
  '',
  '# In-memory TTL cache: 5 menit untuk data 15M, 30 menit untuk data 1H',
  '_ohlcv_cache = TTLCache(maxsize=100, ttl=300)',
  '',
  'async def fetch_ohlcv_with_backoff(pair: str, tf: str, retries: int = 4):',
  '    cache_key = f"{pair}_{tf}"',
  '    if cache_key in _ohlcv_cache:',
  '        return _ohlcv_cache[cache_key]  # HIT: no API call',
  '    ',
  '    for attempt in range(retries):',
  '        try:',
  '            data = await _fetch_from_api(pair, tf)',
  '            _ohlcv_cache[cache_key] = data  # store in cache',
  '            return data',
  '        except RateLimitError:',
  '            wait = (2 ** attempt) + random.uniform(0, 1)  # jitter',
  '            await asyncio.sleep(wait)',
  '    raise DataFetchError(f"Gagal fetch {pair} setelah {retries} percobaan")',
]));

children.push(spacer(80));
children.push(h3('C. Gemini API Rate Limit'));
children.push(para('Gemini free tier: 15 RPM (request per minute), 1 juta token/hari. Untuk produk ini, implementasi token bucket algorithm.'));
children.push(spacer(60));
children.push(...codeBlock([
  '# core/gemini_client.py — Token Bucket Rate Limiter',
  '',
  'import asyncio, time',
  '',
  'class GeminiRateLimiter:',
  '    """Token bucket: max 12 req/menit (safety margin dari limit 15)."""',
  '    ',
  '    def __init__(self, rpm: int = 12):',
  '        self.rpm = rpm',
  '        self.tokens = rpm',
  '        self.last_refill = time.monotonic()',
  '        self._lock = asyncio.Lock()',
  '    ',
  '    async def acquire(self):',
  '        async with self._lock:',
  '            now = time.monotonic()',
  '            elapsed = now - self.last_refill',
  '            # Refill tokens proportional to elapsed time',
  '            refill = int(elapsed * (self.rpm / 60))',
  '            self.tokens = min(self.rpm, self.tokens + refill)',
  '            self.last_refill = now',
  '            if self.tokens < 1:',
  '                wait_time = 60 / self.rpm',
  '                await asyncio.sleep(wait_time)',
  '            self.tokens -= 1',
]));
children.push(pageBreak());

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 3 — DATABASE DESIGN
// ══════════════════════════════════════════════════════════════════════════════
children.push(h1('3. Database Design (PostgreSQL)'));
children.push(para('Menggunakan PostgreSQL via Supabase (managed), diakses dengan asyncpg untuk operasi non-blocking. Connection pool dikonfigurasi dengan max 10 koneksi untuk VPS kecil.'));

children.push(spacer(80));
children.push(h2('3.1 ERD Overview'));
children.push(...codeBlock([
  '  ┌──────────────────┐     ┌──────────────────────┐     ┌───────────────────┐',
  '  │   whitelist_users │     │    signal_log         │     │  backtest_results  │',
  '  ├──────────────────┤     ├──────────────────────┤     ├───────────────────┤',
  '  │ user_id (PK)     │─1──◄│ user_id (FK)          │     │ id (PK, UUID)     │',
  '  │ telegram_id      │     │ id (PK, UUID)         │     │ user_id (FK)      │',
  '  │ username         │     │ pair                  │     │ pair              │',
  '  │ is_active        │     │ direction (L/S)       │     │ timeframe         │',
  '  │ risk_pct         │     │ entry_price           │     │ strategy_params   │',
  '  │ capital_usd      │     │ sl_price              │     │ win_rate          │',
  '  │ created_at       │     │ tp1_price             │     │ net_pnl           │',
  '  │ last_seen        │     │ tp2_price             │     │ max_drawdown      │',
  '  └──────────────────┘     │ lot_size              │     │ total_trades      │',
  '                           │ signal_source         │     │ sharpe_ratio      │',
  '                           │ ai_confidence         │     │ ran_at            │',
  '                           │ outcome               │     │ duration_seconds  │',
  '                           │ created_at            │     └───────────────────┘',
  '                           │ closed_at             │',
  '                           └──────────────────────┘',
]));

children.push(spacer(120));
children.push(h2('3.2 DDL Schema Lengkap'));

children.push(...codeBlock([
  '-- ═══════════════════════════════════════════════════════════════',
  '-- TABLE 1: whitelist_users',
  '-- ═══════════════════════════════════════════════════════════════',
  'CREATE TABLE whitelist_users (',
  '    user_id        BIGINT PRIMARY KEY,        -- Telegram User ID',
  '    telegram_id    BIGINT UNIQUE NOT NULL,',
  '    username       VARCHAR(64),',
  '    full_name      VARCHAR(128),',
  '    is_active      BOOLEAN DEFAULT TRUE,',
  '    risk_pct       DECIMAL(4,2) DEFAULT 1.00, -- % risiko per trade',
  '    capital_usd    DECIMAL(12,2) DEFAULT 1000.00,',
  '    created_at     TIMESTAMPTZ DEFAULT NOW(),',
  '    last_seen      TIMESTAMPTZ',
  ');',
  '',
  '-- ═══════════════════════════════════════════════════════════════',
  '-- TABLE 2: signal_log',
  '-- ═══════════════════════════════════════════════════════════════',
  'CREATE TABLE signal_log (',
  '    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),',
  '    user_id        BIGINT REFERENCES whitelist_users(user_id),',
  '    pair           VARCHAR(12) NOT NULL,        -- e.g., "XAUUSD"',
  '    timeframe      VARCHAR(6) NOT NULL,         -- e.g., "H1", "M15"',
  '    direction      VARCHAR(5) NOT NULL,         -- "LONG" | "SHORT"',
  '    entry_price    DECIMAL(18,5) NOT NULL,',
  '    sl_price       DECIMAL(18,5) NOT NULL,',
  '    tp1_price      DECIMAL(18,5) NOT NULL,      -- RRR 1:1.5',
  '    tp2_price      DECIMAL(18,5),               -- RRR 1:2',
  '    lot_size       DECIMAL(8,2),',
  '    atr_value      DECIMAL(18,6),               -- ATR saat sinyal',
  '    signal_source  VARCHAR(20) DEFAULT \'PUSH\', -- "PUSH" | "PULL"',
  '    ai_confidence  DECIMAL(4,3),                -- 0.0 – 1.0',
  '    ai_reasoning   TEXT,                        -- Gemini raw reasoning',
  '    outcome        VARCHAR(10),                 -- "TP1"|"TP2"|"SL"|"OPEN"',
  '    exit_price     DECIMAL(18,5),',
  '    pnl_pips       DECIMAL(10,2),',
  '    created_at     TIMESTAMPTZ DEFAULT NOW(),',
  '    closed_at      TIMESTAMPTZ',
  ');',
  '',
  'CREATE INDEX idx_signal_log_pair ON signal_log(pair);',
  'CREATE INDEX idx_signal_log_user ON signal_log(user_id);',
  'CREATE INDEX idx_signal_log_created ON signal_log(created_at DESC);',
  '',
  '-- ═══════════════════════════════════════════════════════════════',
  '-- TABLE 3: backtest_results',
  '-- ═══════════════════════════════════════════════════════════════',
  'CREATE TABLE backtest_results (',
  '    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),',
  '    user_id         BIGINT REFERENCES whitelist_users(user_id),',
  '    pair            VARCHAR(12) NOT NULL,',
  '    timeframe       VARCHAR(6) NOT NULL,',
  '    period_years    SMALLINT NOT NULL,',
  '    strategy_params JSONB,                      -- EMA periods, RSI levels, dll',
  '    win_rate        DECIMAL(6,3),               -- 0.0 – 100.0 %',
  '    net_pnl_pct     DECIMAL(10,4),              -- % return dari capital',
  '    max_drawdown    DECIMAL(6,3),               -- % max equity drawdown',
  '    total_trades    INTEGER,',
  '    winning_trades  INTEGER,',
  '    losing_trades   INTEGER,',
  '    avg_rrr         DECIMAL(6,3),               -- Average Risk/Reward realized',
  '    sharpe_ratio    DECIMAL(8,4),',
  '    sortino_ratio   DECIMAL(8,4),',
  '    raw_report_json JSONB,                      -- Full vectorbt report',
  '    ran_at          TIMESTAMPTZ DEFAULT NOW(),',
  '    duration_sec    DECIMAL(8,2)',
  ');',
  '',
  '-- ═══════════════════════════════════════════════════════════════',
  '-- TABLE 4: news_cache (opsional, kurangi re-fetch)',
  '-- ═══════════════════════════════════════════════════════════════',
  'CREATE TABLE news_cache (',
  '    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),',
  '    source         VARCHAR(50),',
  '    headline       TEXT NOT NULL,',
  '    impact         VARCHAR(10),                 -- "HIGH"|"MEDIUM"|"LOW"',
  '    currency       VARCHAR(6),                  -- "USD","EUR","GBP" dst.',
  '    event_time     TIMESTAMPTZ,',
  '    ai_sentiment   VARCHAR(10),                 -- "BULLISH"|"BEARISH"|"NEUTRAL"',
  '    ai_summary     TEXT,',
  '    fetched_at     TIMESTAMPTZ DEFAULT NOW()',
  ');',
  '',
  'CREATE INDEX idx_news_currency ON news_cache(currency);',
  'CREATE INDEX idx_news_event ON news_cache(event_time DESC);',
]));
children.push(pageBreak());

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 4 — RISK MANAGEMENT ENGINE
// ══════════════════════════════════════════════════════════════════════════════
children.push(h1('4. Risk Management Engine'));
children.push(callout('Core Requirement:', 'Ini adalah komponen paling kritis. Setiap sinyal TANPA paket risiko lengkap (SL+TP+LotSize) dianggap INVALID dan tidak akan dikirimkan ke user.'));

children.push(spacer(80));
children.push(h2('4.1 Konsep & Formula'));

children.push(h3('A. Dynamic Stop Loss berbasis ATR'));
children.push(para([
  { text: 'ATR (Average True Range) ', bold: true },
  { text: 'mengukur volatilitas rata-rata candle dalam N periode. SL ditempatkan di luar noise pasar, bukan di angka acak.' },
]));
children.push(spacer(60));
children.push(new Table({
  width: { size: 9000, type: WidthType.DXA },
  columnWidths: [3000, 6000],
  rows: [
    headerRow(['Parameter', 'Formula / Penjelasan'], [3000, 6000]),
    dataRow(['ATR Period', 'Default 14 candle (dapat dikonfigurasi per pair)'], [3000, 6000], true),
    dataRow(['ATR Multiplier', '1.5× untuk scalp/M15, 2.0× untuk swing/H4, 2.5× untuk D1'], [3000, 6000], false),
    dataRow(['SL Long', 'entry_price − (ATR × multiplier)'], [3000, 6000], true),
    dataRow(['SL Short', 'entry_price + (ATR × multiplier)'], [3000, 6000], false),
    dataRow(['SL Distance (pips)', '|entry_price − sl_price| / pip_value_per_unit'], [3000, 6000], true),
  ],
}));

children.push(spacer(80));
children.push(h3('B. Take Profit berbasis Risk/Reward Ratio'));
children.push(new Table({
  width: { size: 9000, type: WidthType.DXA },
  columnWidths: [2500, 3250, 3250],
  rows: [
    headerRow(['Level', 'Formula', 'Tujuan'], [2500, 3250, 3250]),
    dataRow(['TP1 (Partial Close)', 'entry + (risk × 1.5) — Long', 'Amankan profit awal, geser SL ke BE'], [2500, 3250, 3250], true),
    dataRow(['TP2 (Full Close)', 'entry + (risk × 2.0) — Long', 'Target penuh, biarkan berjalan'], [2500, 3250, 3250], false),
    dataRow(['BE (Break Even)', 'Geser SL ke entry setelah TP1 hit', 'Hilangkan risiko kerugian'], [2500, 3250, 3250], true),
  ],
}));

children.push(spacer(80));
children.push(h3('C. Lot Sizing Berdasarkan % Capital Risk'));
children.push(...codeBlock([
  '  risk_amount      = capital_usd × (risk_pct / 100)',
  '  sl_distance_pips = |entry_price - sl_price| / pip_size',
  '  pip_value        = contract_size × pip_size   # e.g., 100000 × 0.0001 = $10/pip (standar lot)',
  '  lot_size         = risk_amount / (sl_distance_pips × pip_value)',
  '',
  '  Contoh EURUSD:',
  '    capital      = $5,000,  risk_pct = 1% → risk_amount = $50',
  '    entry        = 1.08500, SL = 1.08200 → sl_distance = 30 pips',
  '    pip_value    = $10/pip (1 standard lot)',
  '    lot_size     = 50 / (30 × 10) = 0.17 lots',
]));

children.push(spacer(120));
children.push(h2('4.2 Pseudocode Risk Engine'));
children.push(...codeBlock([
  '# engines/risk_engine.py',
  '',
  'from dataclasses import dataclass',
  'from decimal import Decimal',
  'import pandas as pd',
  'import pandas_ta as ta',
  '',
  '@dataclass',
  'class RiskPackage:',
  '    pair: str',
  '    direction: str          # "LONG" | "SHORT"',
  '    entry_price: float',
  '    sl_price: float',
  '    tp1_price: float        # RRR 1:1.5',
  '    tp2_price: float        # RRR 1:2',
  '    lot_size: float',
  '    sl_pips: float',
  '    atr_value: float',
  '    risk_amount_usd: float',
  '    rrr_tp1: float          # actual computed RRR',
  '    rrr_tp2: float',
  '',
  '',
  'class RiskManagementEngine:',
  '',
  '    # Pip size per pair',
  '    PIP_SIZES = {',
  '        "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01,',
  '        "XAUUSD": 0.01,   "BTCUSD": 1.0,',
  '    }',
  '    ',
  '    # ATR multiplier per timeframe',
  '    ATR_MULT = {"M15": 1.5, "H1": 1.75, "H4": 2.0, "D1": 2.5}',
  '',
  '    def compute_atr(self, ohlcv: pd.DataFrame, period: int = 14) -> float:',
  '        """Hitung ATR dari dataframe OHLCV menggunakan pandas_ta."""',
  '        atr_series = ta.atr(ohlcv["High"], ohlcv["Low"],',
  '                            ohlcv["Close"], length=period)',
  '        return float(atr_series.iloc[-1])',
  '',
  '    def compute_pip_value(self, pair: str, lot_size: float = 1.0) -> float:',
  '        """Nilai 1 pip dalam USD untuk 1 standard lot."""',
  '        pip_size = self.PIP_SIZES.get(pair, 0.0001)',
  '        if pair.endswith("USD") and not pair.startswith("USD"):',
  '            return 10.0 * lot_size  # direct pair: $10/pip per lot',
  '        # Untuk pair lain, butuh conversion (simplified)',
  '        return 10.0 * lot_size',
  '',
  '    def calculate(self,',
  '                  pair: str,',
  '                  direction: str,',
  '                  entry_price: float,',
  '                  ohlcv: pd.DataFrame,',
  '                  capital_usd: float,',
  '                  risk_pct: float,',
  '                  timeframe: str = "H1") -> RiskPackage:',
  '',
  '        atr = self.compute_atr(ohlcv)',
  '        mult = self.ATR_MULT.get(timeframe, 1.75)',
  '        pip_size = self.PIP_SIZES.get(pair, 0.0001)',
  '',
  '        # ── Stop Loss ──────────────────────────────────────────────',
  '        sl_distance = atr * mult',
  '        sl_price = (entry_price - sl_distance if direction == "LONG"',
  '                    else entry_price + sl_distance)',
  '',
  '        # ── Take Profit ────────────────────────────────────────────',
  '        risk_dist = abs(entry_price - sl_price)',
  '        tp1_price = (entry_price + risk_dist * 1.5 if direction == "LONG"',
  '                     else entry_price - risk_dist * 1.5)',
  '        tp2_price = (entry_price + risk_dist * 2.0 if direction == "LONG"',
  '                     else entry_price - risk_dist * 2.0)',
  '',
  '        # ── Lot Sizing ─────────────────────────────────────────────',
  '        risk_amount = capital_usd * (risk_pct / 100)',
  '        sl_pips = sl_distance / pip_size',
  '        pip_value_per_lot = self.compute_pip_value(pair)',
  '        lot_size = risk_amount / (sl_pips * pip_value_per_lot)',
  '        lot_size = round(max(0.01, lot_size), 2)  # min 0.01, round 2dp',
  '',
  '        return RiskPackage(',
  '            pair=pair, direction=direction, entry_price=entry_price,',
  '            sl_price=round(sl_price, 5), tp1_price=round(tp1_price, 5),',
  '            tp2_price=round(tp2_price, 5), lot_size=lot_size,',
  '            sl_pips=round(sl_pips, 1), atr_value=round(atr, 6),',
  '            risk_amount_usd=round(risk_amount, 2),',
  '            rrr_tp1=1.5, rrr_tp2=2.0',
  '        )',
]));
children.push(pageBreak());

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 5 — BACKTEST ENGINE
// ══════════════════════════════════════════════════════════════════════════════
children.push(h1('5. Backtest Engine (Quant Core)'));

children.push(h2('5.1 Alasan Memilih vectorbt'));
children.push(new Table({
  width: { size: 9000, type: WidthType.DXA },
  columnWidths: [2200, 3400, 3400],
  rows: [
    headerRow(['Kriteria', 'vectorbt', 'backtrader'], [2200, 3400, 3400]),
    dataRow(['Paradigma', 'Vectorized (NumPy/Pandas seluruh dataset sekaligus)', 'Event-driven (loop per candle)'], [2200, 3400, 3400], true),
    dataRow(['Kecepatan (5 tahun D1)', '< 1 detik', '15–60 detik'], [2200, 3400, 3400], false),
    dataRow(['RAM Usage', '~50–200 MB (efficient array ops)', '~20–80 MB (lebih hemat single run)'], [2200, 3400, 3400], true),
    dataRow(['Cocok untuk', 'Parameter sweep, banyak kombinasi', 'Single strategy, custom logic kompleks'], [2200, 3400, 3400], false),
    dataRow(['Output Metrik', 'Built-in: Sharpe, Sortino, Drawdown, dll.', 'Perlu library tambahan'], [2200, 3400, 3400], true),
    dataRow(['Verdict', '✅ DIPILIH — 100× lebih cepat', '❌ Terlalu lambat untuk UX bot'], [2200, 3400, 3400], false),
  ],
}));

children.push(spacer(100));
children.push(callout('RAM Warning:', 'vectorbt untuk data H1 5 tahun (~43.800 candle) butuh ~200MB RAM per run. Batasi max_workers=2 di ProcessPoolExecutor dan enforce max 2 tahun untuk pair dengan TF < H1.'));

children.push(spacer(80));
children.push(h2('5.2 Strategi yang Di-backtest'));
children.push(para('Strategi default: "Triple Confirmation Strategy" — sinyal entry baru valid jika KETIGA kondisi berikut terpenuhi secara bersamaan:'));
children.push(spacer(60));
children.push(new Table({
  width: { size: 9000, type: WidthType.DXA },
  columnWidths: [1800, 3000, 4200],
  rows: [
    headerRow(['Konfirmasi', 'Indikator', 'Kondisi Entry'], [1800, 3000, 4200]),
    dataRow(['#1 Trend', 'EMA 20 vs EMA 50', 'Long: EMA20 > EMA50 | Short: EMA20 < EMA50'], [1800, 3000, 4200], true),
    dataRow(['#2 Momentum', 'RSI (14)', 'Long: RSI > 50 & < 70 | Short: RSI < 50 & > 30'], [1800, 3000, 4200], false),
    dataRow(['#3 Entry Confirm', 'MACD Crossover', 'Long: MACD line cross above signal | Short: vice versa'], [1800, 3000, 4200], true),
    dataRow(['SL/TP', 'ATR (14)', 'Dinamis sesuai Risk Engine (Section 4)'], [1800, 3000, 4200], false),
  ],
}));

children.push(spacer(80));
children.push(h2('5.3 Pseudocode Backtest Engine'));
children.push(...codeBlock([
  '# engines/backtest_engine.py',
  '# NOTE: Fungsi ini dijalankan di subprocess terpisah — JANGAN gunakan',
  '#       asyncio di dalamnya. Return plain dict, bukan coroutine.',
  '',
  'import pandas as pd',
  'import pandas_ta as ta',
  'import vectorbt as vbt',
  'from dataclasses import dataclass, asdict',
  '',
  '@dataclass',
  'class BacktestReport:',
  '    pair: str',
  '    timeframe: str',
  '    win_rate: float',
  '    net_pnl_pct: float',
  '    max_drawdown: float',
  '    total_trades: int',
  '    winning_trades: int',
  '    losing_trades: int',
  '    avg_rrr: float',
  '    sharpe_ratio: float',
  '    sortino_ratio: float',
  '',
  '',
  'def run_backtest(pair: str,',
  '                 timeframe: str,',
  '                 period_years: int = 3,',
  '                 ema_fast: int = 20,',
  '                 ema_slow: int = 50,',
  '                 rsi_period: int = 14,',
  '                 atr_mult: float = 1.75) -> dict:',
  '    """',
  '    Sync function untuk dijalankan di ProcessPoolExecutor.',
  '    Menggunakan vectorbt untuk vectorized simulation.',
  '    """',
  '    # ── 1. FETCH HISTORICAL DATA ───────────────────────────────',
  '    df = _fetch_historical_ohlcv(pair, timeframe, period_years)',
  '    # df harus memiliki kolom: Open, High, Low, Close, Volume',
  '    # Index: DatetimeIndex',
  '',
  '    # ── 2. COMPUTE INDICATORS ──────────────────────────────────',
  '    df["ema_fast"] = ta.ema(df["Close"], length=ema_fast)',
  '    df["ema_slow"] = ta.ema(df["Close"], length=ema_slow)',
  '    df["rsi"]      = ta.rsi(df["Close"], length=rsi_period)',
  '    df["atr"]      = ta.atr(df["High"], df["Low"], df["Close"], length=14)',
  '    macd_df        = ta.macd(df["Close"])',
  '    df["macd"]     = macd_df[f"MACD_12_26_9"]',
  '    df["macd_sig"] = macd_df[f"MACDs_12_26_9"]',
  '    df = df.dropna()',
  '',
  '    # ── 3. GENERATE ENTRY SIGNALS (vectorized boolean array) ────',
  '    trend_bull  = df["ema_fast"] > df["ema_slow"]',
  '    trend_bear  = df["ema_fast"] < df["ema_slow"]',
  '    rsi_ok_long = (df["rsi"] > 50) & (df["rsi"] < 70)',
  '    rsi_ok_shrt = (df["rsi"] < 50) & (df["rsi"] > 30)',
  '    macd_cross_up   = (df["macd"] > df["macd_sig"]) &',
  '                      (df["macd"].shift(1) <= df["macd_sig"].shift(1))',
  '    macd_cross_down = (df["macd"] < df["macd_sig"]) &',
  '                      (df["macd"].shift(1) >= df["macd_sig"].shift(1))',
  '',
  '    long_entries  = trend_bull & rsi_ok_long & macd_cross_up',
  '    short_entries = trend_bear & rsi_ok_shrt & macd_cross_down',
  '',
  '    # ── 4. DYNAMIC SL/TP (ATR-based) ───────────────────────────',
  '    sl_stop  = df["atr"] * atr_mult / df["Close"]  # as % of price',
  '    tp1_take = sl_stop * 1.5',
  '    tp2_take = sl_stop * 2.0',
  '',
  '    # ── 5. RUN VECTORBT PORTFOLIO SIM ──────────────────────────',
  '    portfolio = vbt.Portfolio.from_signals(',
  '        close          = df["Close"],',
  '        entries        = long_entries,',
  '        exits          = short_entries,     # exit long when short signal',
  '        short_entries  = short_entries,',
  '        short_exits    = long_entries,',
  '        sl_stop        = sl_stop,',
  '        tp_stop        = tp2_take,          # use TP2 for max profit',
  '        init_cash      = 10_000.0,',
  '        fees           = 0.0002,            # 0.02% per trade (spread simulation)',
  '        slippage       = 0.0001,',
  '    )',
  '',
  '    # ── 6. EXTRACT METRICS ─────────────────────────────────────',
  '    stats = portfolio.stats()',
  '    trades = portfolio.trades.records_readable',
  '    ',
  '    total  = len(trades)',
  '    wins   = (trades["PnL"] > 0).sum()',
  '    losses = (trades["PnL"] <= 0).sum()',
  '',
  '    return asdict(BacktestReport(',
  '        pair         = pair,',
  '        timeframe    = timeframe,',
  '        win_rate     = round(float(wins / total * 100) if total > 0 else 0, 2),',
  '        net_pnl_pct  = round(float(stats["Total Return [%]"]), 4),',
  '        max_drawdown = round(float(stats["Max Drawdown [%]"]), 3),',
  '        total_trades = int(total),',
  '        winning_trades = int(wins),',
  '        losing_trades  = int(losses),',
  '        avg_rrr      = round(float(trades["PnL"].mean()), 3),',
  '        sharpe_ratio = round(float(stats["Sharpe Ratio"]), 4),',
  '        sortino_ratio= round(float(stats["Sortino Ratio"]), 4),',
  '    ))',
]));

children.push(spacer(80));
children.push(h2('5.4 RAM Management saat Backtest'));
children.push(new Table({
  width: { size: 9000, type: WidthType.DXA },
  columnWidths: [2500, 3000, 3500],
  rows: [
    headerRow(['Teknik', 'Implementasi', 'Efek'], [2500, 3000, 3500]),
    dataRow(['Chunked Loading', 'Muat data per tahun, concat lalu drop chunk', 'Peak RAM turun 40%'], [2500, 3000, 3500], true),
    dataRow(['dtype Optimization', 'float32 untuk OHLCV, bool untuk signals', 'RAM turun hingga 50%'], [2500, 3000, 3500], false),
    dataRow(['GC Explicit', 'gc.collect() setelah portfolio.stats()', 'Bebaskan memori segera'], [2500, 3000, 3500], true),
    dataRow(['Period Cap', 'Max 2 tahun untuk TF < H1, max 5 tahun untuk D1', 'Batas atas ~300MB/run'], [2500, 3000, 3500], false),
    dataRow(['ProcessPool Limit', 'max_workers=2, queue maxsize=5', 'Cegah fork storm'], [2500, 3000, 3500], true),
  ],
}));
children.push(pageBreak());

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 6 — DIRECTORY STRUCTURE
// ══════════════════════════════════════════════════════════════════════════════
children.push(h1('6. Struktur Direktori Proyek'));
children.push(...codeBlock([
  'forex-ai-copilot/',
  '├── 📄 docker-compose.yml',
  '├── 📄 Dockerfile',
  '├── 📄 .env                         # Secrets (TIDAK di-commit ke Git)',
  '├── 📄 .env.example',
  '├── 📄 requirements.txt',
  '├── 📄 pyproject.toml',
  '│',
  '├── 📁 bot/',
  '│   ├── 📄 main.py                  # Entry point: start aiogram polling/webhook',
  '│   ├── 📄 config.py                # Pydantic settings dari env vars',
  '│   │',
  '│   ├── 📁 handlers/                # Telegram command handlers',
  '│   │   ├── 📄 __init__.py',
  '│   │   ├── 📄 analisa.py           # /analisa [PAIR]',
  '│   │   ├── 📄 backtest.py          # /backtest [PAIR] [TF]',
  '│   │   ├── 📄 signal_push.py       # Push sinyal otomatis (scheduler)',
  '│   │   └── 📄 admin.py             # /adduser /removeuser /setrisk',
  '│   │',
  '│   ├── 📁 middlewares/',
  '│   │   ├── 📄 whitelist.py         # Cek whitelist_users sebelum handler',
  '│   │   └── 📄 rate_limiter.py      # Per-user rate limiting',
  '│   │',
  '│   └── 📁 keyboards/',
  '│       └── 📄 inline.py            # Inline keyboard markups',
  '│',
  '├── 📁 core/',                          
  '│   ├── 📄 job_queue.py             # BacktestJobQueue (asyncio + ProcessPool)',
  '│   ├── 📄 scheduler.py             # APScheduler untuk push sinyal',
  '│   ├── 📄 gemini_client.py         # Wrapper Gemini API + rate limiter',
  '│   └── 📄 telegram_formatter.py    # Format pesan sinyal untuk Telegram',
  '│',
  '├── 📁 engines/',
  '│   ├── 📄 risk_engine.py           # ATR-SL, RRR-TP, Lot Sizing',
  '│   ├── 📄 technical_engine.py      # EMA, RSI, MACD, Confluence Score',
  '│   ├── 📄 backtest_engine.py       # vectorbt simulation (sync, no asyncio)',
  '│   └── 📄 fundamental_engine.py    # News/kalender ekonomi + Gemini sentiment',
  '│',
  '├── 📁 data/',
  '│   ├── 📄 price_fetcher.py         # OHLCV fetcher + TTL cache',
  '│   └── 📄 news_fetcher.py          # Economic calendar scraper',
  '│',
  '├── 📁 db/',
  '│   ├── 📄 connection.py            # asyncpg pool init & teardown',
  '│   ├── 📄 models.py                # Dataclass models (mirror DB schema)',
  '│   ├── 📄 queries.py               # Typed async query functions',
  '│   └── 📄 migrations/',
  '│       └── 📄 001_init.sql         # DDL schema awal',
  '│',
  '└── 📁 tests/',
  '    ├── 📄 test_risk_engine.py',
  '    ├── 📄 test_backtest_engine.py',
  '    └── 📄 test_technical_engine.py',
]));

children.push(pageBreak());

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 7 — MESSAGE FORMAT
// ══════════════════════════════════════════════════════════════════════════════
children.push(h1('7. Format Pesan Telegram'));

children.push(h2('7.1 Format Sinyal Push (PUSH Mode)'));
children.push(...codeBlock([
  '┌─────────────────────────────────────────┐',
  '│  🚨 SIGNAL ALERT — XAUUSD (GOLD)        │',
  '│  ═══════════════════════════════════    │',
  '│  📈 Direction  : LONG                   │',
  '│  ⏰ Timeframe  : H1                     │',
  '│  🎯 Entry Price: 2,345.50               │',
  '│                                         │',
  '│  🛡️ Stop Loss  : 2,331.80  (−13.7 pips) │',
  '│  🎯 TP 1       : 2,366.55  (+21.0 pips) │',
  '│  🏆 TP 2       : 2,373.90  (+28.4 pips) │',
  '│                                         │',
  '│  📊 Risk/Reward : TP1=1:1.5 | TP2=1:2.0 │',
  '│  💰 Lot Size   : 0.17 lots              │',
  '│     (Risk $50 | 1% of $5,000 capital)   │',
  '│                                         │',
  '│  📰 Reasoning:                          │',
  '│  NFP data lebih kuat dari ekspektasi.   │',
  '│  DXY melemah, Gold sentiment bullish.   │',
  '│  EMA20 > EMA50, RSI 58, MACD positif.  │',
  '│                                         │',
  '│  🤖 AI Confidence: 78%                  │',
  '│  ⏱️  Signal Time : 2025-06-15 14:00 WIB │',
  '└─────────────────────────────────────────┘',
]));

children.push(spacer(80));
children.push(h2('7.2 Format Report Backtest (/backtest)'));
children.push(...codeBlock([
  '┌──────────────────────────────────────────┐',
  '│  📊 BACKTEST REPORT — XAUUSD H4          │',
  '│  Period: 3 Tahun (2022–2025)             │',
  '│  Strategy: Triple Confirmation           │',
  '│  ══════════════════════════════════════  │',
  '│                                          │',
  '│  📈 Total Trades   : 187                 │',
  '│  ✅ Winning Trades : 112  (59.9%)        │',
  '│  ❌ Losing Trades  : 75   (40.1%)        │',
  '│                                          │',
  '│  💰 Net PnL        : +34.7%              │',
  '│  📉 Max Drawdown   : −12.3%              │',
  '│  📊 Sharpe Ratio   : 1.42                │',
  '│  📊 Sortino Ratio  : 1.87                │',
  '│  ⚖️  Avg RRR       : 1.73                │',
  '│                                          │',
  '│  ⏱️  Computation   : 2.3 detik           │',
  '│  💾 Backtest saved to DB ✓               │',
  '└──────────────────────────────────────────┘',
]));
children.push(pageBreak());

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 8 — DEPLOYMENT
// ══════════════════════════════════════════════════════════════════════════════
children.push(h1('8. Development & Deployment Phases'));

children.push(h2('Phase 1 — Setup Dev Environment (Google Antigravity Cloud IDE)'));
children.push(numList('Clone repository dan masuk ke direktori proyek.'));
children.push(numList('Buat file .env dari .env.example dan isi: TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, DATABASE_URL (Supabase), WHITELIST_USER_IDS.'));
children.push(numList('Install dependencies: pip install -r requirements.txt'));
children.push(numList('Jalankan migrasi DB: python -m db.migrations'));
children.push(numList('Test bot lokal: python bot/main.py (polling mode)'));
children.push(numList('Jalankan unit test: pytest tests/ -v'));
children.push(spacer(80));

children.push(h2('Phase 2 — Dockerisasi'));
children.push(...codeBlock([
  '# Dockerfile',
  'FROM python:3.11-slim',
  '',
  '# Install system deps (ta-lib membutuhkan gcc)',
  'RUN apt-get update && apt-get install -y gcc g++ && rm -rf /var/lib/apt/lists/*',
  '',
  'WORKDIR /app',
  'COPY requirements.txt .',
  'RUN pip install --no-cache-dir -r requirements.txt',
  '',
  'COPY . .',
  '',
  '# Non-root user untuk keamanan',
  'RUN useradd -m botuser && chown -R botuser:botuser /app',
  'USER botuser',
  '',
  'CMD ["python", "bot/main.py"]',
  '',
  '---',
  '',
  '# docker-compose.yml',
  'version: "3.9"',
  'services:',
  '  bot:',
  '    build: .',
  '    restart: unless-stopped',
  '    env_file: .env',
  '    depends_on:',
  '      postgres:',
  '        condition: service_healthy',
  '    deploy:',
  '      resources:',
  '        limits:',
  '          memory: 1500M     # Hard cap — cegah OOM',
  '          cpus: "1.5"',
  '',
  '  postgres:',
  '    image: postgres:15-alpine',
  '    restart: unless-stopped',
  '    environment:',
  '      POSTGRES_DB: forex_bot',
  '      POSTGRES_USER: ${DB_USER}',
  '      POSTGRES_PASSWORD: ${DB_PASS}',
  '    volumes:',
  '      - postgres_data:/var/lib/postgresql/data',
  '      - ./db/migrations:/docker-entrypoint-initdb.d',
  '    healthcheck:',
  '      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]',
  '      interval: 10s',
  '      timeout: 5s',
  '      retries: 5',
  '',
  'volumes:',
  '  postgres_data:',
]));

children.push(spacer(80));
children.push(h2('Phase 3 — Deploy ke Linux VPS'));
children.push(numList('SSH ke VPS: ssh user@vps-ip'));
children.push(numList('Install Docker: curl -fsSL https://get.docker.com | sh && usermod -aG docker $USER'));
children.push(numList('Clone repo ke VPS: git clone <repo-url> && cd forex-ai-copilot'));
children.push(numList('Copy file .env ke VPS (JANGAN commit secrets ke Git): scp .env user@vps-ip:/path/to/project/'));
children.push(numList('Build dan start: docker compose up -d --build'));
children.push(numList('Verifikasi running: docker compose ps && docker compose logs -f bot'));
children.push(numList('Setup auto-restart on reboot: systemctl enable docker (sudah default di Docker)'));
children.push(spacer(80));
children.push(callout('Security Hardening:', 'Aktifkan UFW firewall, hanya buka port 22 (SSH) dan 443 (jika webhook). Jangan ekspos port Postgres ke publik. Gunakan Fail2ban untuk brute-force protection.'));

children.push(spacer(80));
children.push(h2('Phase 4 — Monitoring & Observability'));
children.push(new Table({
  width: { size: 9000, type: WidthType.DXA },
  columnWidths: [2500, 3000, 3500],
  rows: [
    headerRow(['Tool', 'Setup', 'Monitor Apa'], [2500, 3000, 3500]),
    dataRow(['docker stats', 'Built-in Docker CLI', 'Real-time CPU & RAM per container'], [2500, 3000, 3500], true),
    dataRow(['Uptime Kuma', 'Docker container terpisah', 'Bot availability, alert via Telegram'], [2500, 3000, 3500], false),
    dataRow(['Python logging', 'JSON structured logging', 'Signal errors, API failures, backtest times'], [2500, 3000, 3500], true),
    dataRow(['PostgreSQL EXPLAIN', 'Manual query analysis', 'Slow query detection'], [2500, 3000, 3500], false),
  ],
}));
children.push(pageBreak());

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 9 — ENVIRONMENT VARIABLES & CONFIG
// ══════════════════════════════════════════════════════════════════════════════
children.push(h1('9. Konfigurasi & Environment Variables'));
children.push(...codeBlock([
  '# .env.example — Copy ke .env dan isi nilai yang sesuai',
  '',
  '# ── Telegram ──────────────────────────────────────────────────',
  'TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather',
  'TELEGRAM_ADMIN_IDS=123456789,987654321   # User ID admin (comma-separated)',
  '',
  '# ── AI Engine ────────────────────────────────────────────────',
  'GEMINI_API_KEY=your_gemini_api_key',
  'GEMINI_MODEL=gemini-1.5-flash            # Flash = cheaper, Pro = smarter',
  '',
  '# ── Database (Supabase / self-hosted Postgres) ────────────────',
  'DATABASE_URL=postgresql://user:pass@host:5432/forex_bot',
  'DB_POOL_MIN=2',
  'DB_POOL_MAX=10',
  '',
  '# ── Price Data API ────────────────────────────────────────────',
  'ALPHA_VANTAGE_KEY=your_key              # Free: 5 req/min, 500 req/day',
  'PRICE_CACHE_TTL_SECONDS=300            # 5 menit cache untuk data real-time',
  '',
  '# ── Risk Engine Defaults ──────────────────────────────────────',
  'DEFAULT_RISK_PCT=1.0                   # 1% risiko per trade',
  'DEFAULT_CAPITAL_USD=5000',
  'DEFAULT_ATR_PERIOD=14',
  '',
  '# ── Scheduler (Push Mode) ─────────────────────────────────────',
  'PUSH_SIGNAL_INTERVAL_HOURS=4           # Cek fundamental setiap 4 jam',
  'PUSH_PAIRS=XAUUSD,EURUSD,GBPUSD        # Pair yang dipantau',
  '',
  '# ── Backtest Engine ───────────────────────────────────────────',
  'BACKTEST_MAX_WORKERS=2',
  'BACKTEST_MAX_QUEUE_SIZE=5',
  'BACKTEST_MAX_PERIOD_YEARS=5',
  '',
  '# ── Whitelist ─────────────────────────────────────────────────',
  'WHITELIST_USER_IDS=111,222,333         # Bootstrap whitelist (override di DB)',
]));
children.push(pageBreak());

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 10 — TECHNICAL RISKS & MITIGATIONS
// ══════════════════════════════════════════════════════════════════════════════
children.push(h1('10. Technical Risks & Mitigations'));

children.push(new Table({
  width: { size: 9000, type: WidthType.DXA },
  columnWidths: [2200, 2200, 2200, 2400],
  rows: [
    headerRow(['Risk', 'Probability', 'Impact', 'Mitigation'], [2200, 2200, 2200, 2400]),
    dataRow(['OOM Crash saat backtest', 'Medium', 'HIGH', 'Memory limit Docker, ProcessPool cap, dtype optimization'], [2200, 2200, 2200, 2400], true),
    dataRow(['Telegram rate limit hit', 'Low', 'Medium', 'aiogram ThrottlingMiddleware + per-user limiter'], [2200, 2200, 2200, 2400], false),
    dataRow(['Gemini API down/quota habis', 'Low', 'HIGH', 'Fallback: kirim sinyal teknikal saja tanpa AI reasoning'], [2200, 2200, 2200, 2400], true),
    dataRow(['Price data stale/tidak akurat', 'Medium', 'HIGH', 'TTL cache pendek, fallback ke sumber data sekunder'], [2200, 2200, 2200, 2400], false),
    dataRow(['VPS reboot/crash', 'Low', 'Medium', 'docker restart: unless-stopped, signal log di DB (bukan memori)'], [2200, 2200, 2200, 2400], true),
    dataRow(['Database connection pool exhausted', 'Low', 'Medium', 'Pool max=10, query timeout, connection retry logic'], [2200, 2200, 2200, 2400], false),
    dataRow(['Unauthorized user akses', 'Medium', 'HIGH', 'WhitelistMiddleware di-apply SEBELUM semua handler'], [2200, 2200, 2200, 2400], true),
  ],
}));

children.push(spacer(120));
children.push(h2('Rekomendasi VPS Spec'));
children.push(new Table({
  width: { size: 9000, type: WidthType.DXA },
  columnWidths: [2200, 2200, 2300, 2300],
  rows: [
    headerRow(['Tier', 'RAM', 'vCPU', 'Cocok untuk'], [2200, 2200, 2300, 2300]),
    dataRow(['Minimum', '2 GB', '1 vCPU', 'Bot only, max_workers=1, no heavy backtest'], [2200, 2200, 2300, 2300], true),
    dataRow(['Recommended', '4 GB', '2 vCPU', 'Full features, max_workers=2, data 3 tahun'], [2200, 2200, 2300, 2300], false),
    dataRow(['Optimal', '8 GB', '4 vCPU', 'Concurrent backtest, data 5 tahun, Redis cache'], [2200, 2200, 2300, 2300], true),
  ],
}));

children.push(spacer(120));
children.push(h2('Checklist Pre-Launch'));
children.push(bullet('✅ Unit test Risk Engine (edge cases: SL < 0, lot < 0.01, leverage overflow)'));
children.push(bullet('✅ Unit test Backtest Engine (data kosong, pair tidak valid, TF tidak didukung)'));
children.push(bullet('✅ Integration test whitelist middleware (bot HARUS diam untuk non-whitelist user)'));
children.push(bullet('✅ Load test: 3 backtest simultan — pastikan bot masih merespons pesan lain'));
children.push(bullet('✅ Secrets tidak ada di Git history (gunakan git-secrets atau .gitignore ketat)'));
children.push(bullet('✅ Docker resource limit terkonfigurasi di docker-compose.yml'));
children.push(bullet('✅ Database backup schedule aktif (Supabase auto-backup atau pg_dump cron)'));
children.push(bullet('✅ Monitoring alert setup — notifikasi jika bot down > 5 menit'));

children.push(spacer(120));
children.push(sep());
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 120, after: 40 },
  children: [new TextRun({ text: 'Document End — Forex AI Co-Pilot PRD & Technical Architecture v1.0', font: 'Arial', size: 18, color: C.gray, italics: true })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 0, after: 0 },
  children: [new TextRun({ text: 'CONFIDENTIAL — Whitelist Project (2-5 Users) — Not for Distribution', font: 'Arial', size: 17, color: C.red, bold: true })],
}));

// ─────────────────────────────────────────────────────────────────────────────
// BUILD DOCUMENT
// ─────────────────────────────────────────────────────────────────────────────
const doc = new Document({
  numbering: {
    config: [
      {
        reference: 'bullets',
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: '•',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 540, hanging: 260 } } },
        }, {
          level: 1, format: LevelFormat.BULLET, text: '◦',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 900, hanging: 260 } } },
        }],
      },
      {
        reference: 'numbers',
        levels: [{
          level: 0, format: LevelFormat.DECIMAL, text: '%1.',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 540, hanging: 260 } } },
        }],
      },
    ],
  },
  styles: {
    default: {
      document: { run: { font: 'Arial', size: 20, color: C.darkBlue } },
    },
    paragraphStyles: [
      {
        id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 32, bold: true, font: 'Arial', color: C.darkBlue },
        paragraph: { spacing: { before: 400, after: 160 }, outlineLevel: 0 },
      },
      {
        id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 26, bold: true, font: 'Arial', color: C.midBlue },
        paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 1 },
      },
      {
        id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 22, bold: true, font: 'Arial', color: C.accent },
        paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2 },
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: C.accent, space: 1 } },
          children: [
            new TextRun({ text: 'FOREX AI CO-PILOT ', font: 'Arial', size: 17, bold: true, color: C.midBlue }),
            new TextRun({ text: '|  PRD & Technical Architecture  |  CONFIDENTIAL', font: 'Arial', size: 17, color: C.gray }),
          ],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: C.lightGray, space: 1 } },
          tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
          children: [
            new TextRun({ text: 'v1.0 · June 2025', font: 'Arial', size: 16, color: C.gray }),
            new TextRun({ text: '\t', font: 'Arial', size: 16 }),
            new TextRun({ text: 'Page ', font: 'Arial', size: 16, color: C.gray }),
            new TextRun({
              children: [PageNumber.CURRENT],
              font: 'Arial',
              size: 16,
              color: C.gray,
            }),
          ],
        })],
      }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then(buffer => {
  fs.mkdirSync('/mnt/user-data/outputs', { recursive: true });
  fs.writeFileSync('/mnt/user-data/outputs/Forex_AI_CoPilot_PRD_Architecture.docx', buffer);
  console.log('✅ Document generated successfully!');
}).catch(err => {
  console.error('❌ Error:', err);
  process.exit(1);
});