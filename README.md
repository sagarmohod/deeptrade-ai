# DeepTrade AI

> Personal AI-powered algorithmic trading platform for NSE/BSE.
> Designed for a single user, optimized for capital preservation, built with discipline.

---

## What This Is

DeepTrade AI is a complete trading platform that:

- Generates trading signals using ML + technical + fundamental + news agents
- Trades NIFTY/BANKNIFTY/SENSEX options (scalping) and equity (swing/weekly/monthly)
- Runs **paper trading always**, in parallel to live, for unbiased performance comparison
- Enforces strict pre-trade risk gates (capital limits, daily loss limits, kill switch)
- Integrates with Zerodha Kite Connect for execution
- Provides a clean, distraction-free UI in pure white/black/grey (with dark mode)

This is **not** a SaaS, not a copy-trading service, not a signal-selling product. It's a personal tool — designed for one user, with full control and full responsibility.

## Architecture (Two-Tier)

```
┌─────────────────────────────────────┐    ┌─────────────────────────────────┐
│  TIER 1: Mac (development)          │    │  TIER 2: Cloud VPS (live)       │
│                                      │    │  Hostinger Mumbai, static IP    │
│  - Code editor                       │    │                                 │
│  - ML model training (18GB RAM)      │ ─→ │  - Live ingestion (Kite WS)     │
│  - Backtest research                 │    │  - Live order placement         │
│  - UI development                    │    │  - Paper engine (parallel)      │
│  - Paper trading dev                 │    │  - Postgres + Redis + Qdrant    │
└─────────────────────────────────────┘    └─────────────────────────────────┘
```

**During development:** Everything on Mac. No VPS needed.
**For live trading:** Mac for training, VPS for execution.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x async, asyncpg
- **Database:** TimescaleDB (timeseries) + PostgreSQL (OLTP) + Redis (cache/queue) + Qdrant (vector)
- **ML:** LightGBM, sklearn, optuna, FinBERT, PyTorch (MPS for M-series)
- **Broker:** Zerodha Kite Connect (REST + WebSocket via `kiteconnect` SDK)
- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + TanStack Query + shadcn-style components
- **Infra:** Docker Compose (local + VPS)

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your KITE_API_KEY and KITE_API_SECRET

# 2. One-command setup
make setup

# 3. Run the app
make paper           # Terminal 1: backend
make frontend-dev    # Terminal 2: frontend

# 4. Open http://localhost:5173
```

For detailed instructions, see **[RUN_GUIDE.md](RUN_GUIDE.md)**.

## What's Built

| Component | Status |
|---|---|
| Backend models, DB schema, migrations | ✅ |
| Zerodha adapter (orders, margin, quotes) | ✅ |
| Paper trading sim engine (parallel) | ✅ |
| Risk engine (10 gates) | ✅ |
| Order router (paper+live splitter) | ✅ |
| ORB strategy + fake breakout filter | ✅ |
| Connors 2-RSI strategy | ✅ |
| ML training pipeline (LightGBM, walk-forward) | ✅ |
| Model registry + lifecycle | ✅ |
| FastAPI server with all routes | ✅ |
| React UI (9 pages, dark+light mode) | ✅ |
| Docker compose | ✅ |
| Daily Kite OAuth flow | ✅ |
| **PEAD strategy** | 🚧 design done, code skeleton |
| **News + sentiment agent** | 🚧 wired to your internal LLM |
| **Backtesting (vectorbt + nautilus)** | 🚧 |
| **Live VPS deployment** | 🚧 add when ready to go live |

## Documentation

- **[RUN_GUIDE.md](RUN_GUIDE.md)** — Operations guide (setup → paper → training → live)
- **Design docs (in chat history):** v1, v2, v3, v5, v6, v7 — full architectural specification

## Honest Notes

- Most retail F&O traders lose money. This system can't change that — it can only give you a disciplined process.
- 60 days of paper trading before live is non-negotiable.
- Of three starter strategies (ORB, Connors, PEAD), expect 1-2 to pass validation. That's normal.
- Realistic expectations: Sharpe 0.8-1.4, drawdown 10-18%, CAGR 10-20%.
- This is a tool, not a money machine.

## License

Personal use only. Not licensed for redistribution or commercial use.
