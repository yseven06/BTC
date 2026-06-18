# 🧠 TradeMinds AI — Trading Intelligence Platform

<div align="center">

**AI-Powered Multi-Engine Trading Analysis & Signal Generation Platform**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14+-000000?logo=next.js&logoColor=white)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-336791?logo=postgresql&logoColor=white)](https://supabase.com)
[![Redis](https://img.shields.io/badge/Redis-Upstash-DC382D?logo=redis&logoColor=white)](https://upstash.com)

</div>

---

## 📋 Overview

TradeMinds AI is a professional-grade trading intelligence platform that combines **8 analysis engines** into a unified **AI Decision Engine** to generate high-confidence trading signals with detailed explanations.

### Key Features

- 🔮 **Multi-Engine Signal Generation** — 8 specialized engines analyze every asset
- 📊 **Real-Time Market Data** — Binance WebSocket, CoinGecko, Yahoo Finance
- 🎯 **Weighted Scoring System** — Deterministic, data-driven signals
- 💡 **Detailed Explanations** — Every signal includes WHY it was generated
- 📈 **Performance Tracking** — Win rate, returns, and strategy analytics
- 🌍 **Multi-Market** — Crypto + BIST stocks (Forex & Futures in V2)
- 🔐 **Multi-User** — Email + Google authentication
- 🌐 **Bilingual** — Turkish (default) + English

### Analysis Engines

| Engine | Weight | Description |
|--------|--------|-------------|
| Technical Analysis | 20% | EMA, RSI, MACD, Bollinger, ATR, patterns |
| Market Structure | 20% | BOS, CHoCH, HH/HL/LH/LL, trend detection |
| Smart Money (SMC) | 15% | Order blocks, FVG, liquidity zones, breakers |
| Volume Analysis | 15% | Volume profile, POC, accumulation/distribution |
| Candle Range Theory | 10% | HTF range analysis, sweep detection |
| Risk Management | 10% | Volatility, position sizing, R:R |
| Fundamental (Stocks) | 10% | Financial ratios, valuation, sector comparison |
| AI Decision | — | Orchestrates all engines, generates final signal |

### Signal Output

```
Signal: BUY
Confidence: 82% | Probability: 76% | Risk: Medium

✅ Supporting: Market structure bullish, SMC discount zone, volume accumulation
⚠️ Conflicting: RSI approaching overbought
📊 Trade Plan: Entry 67,500 | SL 64,800 | TP1 70,200 | TP2 73,500 | TP3 78,000
❌ Invalidation: Close below 64,800 on 4H timeframe
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                 │
│  Dashboard | Signals | Markets | Watchlist | Alerts  │
└──────────────────────┬──────────────────────────────┘
                       │ REST API + WebSocket
┌──────────────────────┴──────────────────────────────┐
│                   Backend (FastAPI)                   │
│                                                      │
│  ┌─────────┐ ┌──────────┐ ┌─────┐ ┌─────┐ ┌──────┐ │
│  │Technical│ │Mkt Struct│ │ SMC │ │ CRT │ │Volume│ │
│  └────┬────┘ └────┬─────┘ └──┬──┘ └──┬──┘ └──┬───┘ │
│       │           │          │       │        │      │
│  ┌────┴───────────┴──────────┴───────┴────────┴───┐ │
│  │            AI Decision Engine                   │ │
│  │    Weighted Scoring → Signal → Explanation      │ │
│  └─────────────────────┬───────────────────────────┘ │
│                        │                              │
│  ┌─────────────────────┴───────────────────────────┐ │
│  │         Performance Tracking Layer               │ │
│  └──────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
         │                    │
  ┌──────┴──────┐    ┌───────┴───────┐
  │  Supabase   │    │ Upstash Redis │
  │ PostgreSQL  │    │    Cache      │
  └─────────────┘    └───────────────┘
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Supabase account (PostgreSQL)
- Upstash account (Redis)

### Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env.local
# Edit .env.local with your API URL
npm run dev
```

### Environment Variables

See `.env.example` files in both `backend/` and `frontend/` directories.

---

## 📁 Project Structure

```
BTC/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Configuration
│   │   ├── database.py          # Supabase PostgreSQL
│   │   ├── redis_client.py      # Upstash Redis
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── auth/                # JWT + Google OAuth
│   │   ├── api/                 # REST API routes
│   │   ├── collectors/          # Data collectors
│   │   ├── engines/             # Analysis engines
│   │   │   ├── technical/       # TA indicators + patterns
│   │   │   ├── market_structure/# BOS, CHoCH, S/R
│   │   │   ├── smc/            # Smart Money Concepts
│   │   │   ├── crt/            # Candle Range Theory
│   │   │   ├── volume/         # Volume analysis
│   │   │   ├── risk/           # Risk management
│   │   │   ├── fundamental/    # BIST stock fundamentals
│   │   │   └── ai_decision/    # Signal generation
│   │   └── tasks/              # Background tasks
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/                # Next.js pages
│   │   ├── components/         # React components
│   │   ├── hooks/              # Custom hooks
│   │   ├── lib/                # Utilities
│   │   ├── types/              # TypeScript types
│   │   └── i18n/               # Translations
│   └── package.json
└── README.md
```

---

## ⚠️ Disclaimer

This platform is for **educational and analytical purposes only**. It does not constitute financial advice. Trading involves significant risk of loss. Always do your own research and consult with a qualified financial advisor before making investment decisions.

---

## 📄 License

Private — All rights reserved.
