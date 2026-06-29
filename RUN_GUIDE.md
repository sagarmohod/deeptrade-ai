# DeepTrade AI — Run Guide

Complete step-by-step process to get DeepTrade AI running, from zero to live trading.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Initial Setup (one-time)](#2-initial-setup-one-time)
3. [Running the Application](#3-running-the-application)
4. [Daily Operations](#4-daily-operations)
5. [Model Training & Deployment](#5-model-training--deployment)
6. [Going Live (When Ready)](#6-going-live-when-ready)
7. [Troubleshooting](#7-troubleshooting)
8. [File & Directory Reference](#8-file--directory-reference)

---

## 1. Prerequisites

### Required software (install once)

```bash
# Python 3.12+
python3 --version  # should show 3.12.x

# Node.js 20+
node --version     # should show v20.x.x

# Docker Desktop (for Mac)
docker --version
docker compose version

# uv (fast Python package manager)
pip install uv
```

### Required accounts

1. **Zerodha trading account** — open at zerodha.com if you don't have one
2. **Kite Connect developer account** — sign up at https://developers.kite.trade
3. **Subscribe to Kite Connect Paid (₹500/month)** — required for live + historical market data
4. **Create a Kite Connect App:**
   - Go to https://developers.kite.trade/apps
   - Click "Create new app"
   - App type: "Connect"
   - Redirect URL: `http://localhost:8000/api/v1/auth/kite/callback`
   - Note down `API Key` and `API Secret`

### Hardware

- **For development & training:** Your MacBook M3 Pro 18GB
- **For live trading (later):** Cloud VPS in India with static IP (Hostinger KVM 2 ~₹700-900/mo recommended)
- **Note:** During development & paper trading you only need your Mac. VPS is only required for actual live order placement.

---

## 2. Initial Setup (one-time)

### Step 2.1 — Clone & navigate

```bash
cd ~/projects  # or wherever you keep code
# Project should be at ./deeptrade-ai
cd deeptrade-ai
```

### Step 2.2 — Configure environment

```bash
cp .env.example .env
```

Open `.env` in your editor and set:

```bash
# Required for any operation
KITE_API_KEY=your_actual_api_key_here
KITE_API_SECRET=your_actual_api_secret_here

# Keep these defaults for now
MODE=paper
LIVE_TRADING_ENABLED=false   # leave false until ready for live
PAPER_SIMULATED_CAPITAL=1000000
LIVE_DEPLOYED_CAPITAL=15000

# Database password (change for production)
POSTGRES_PASSWORD=your_chosen_password

# Update DATABASE_URL to match POSTGRES_PASSWORD
DATABASE_URL=postgresql+asyncpg://deeptrade:your_chosen_password@localhost:5432/deeptrade
```

### Step 2.3 — Install Python dependencies

```bash
make install
# or manually:
uv pip install -e ".[dev]"
```

This installs the project in editable mode plus dev tools (pytest, ruff, etc).

### Step 2.4 — Start infrastructure (Postgres + Redis + Qdrant)

```bash
docker compose up -d postgres redis qdrant
```

Wait ~10 seconds for Postgres to be ready. Verify:

```bash
docker compose ps
# all three should show "healthy" or "running"
```

### Step 2.5 — Run database migrations

```bash
make migrate
# or: alembic upgrade head
```

This creates all tables. You should see:

```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial, Initial schema
```

### Step 2.6 — Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### Step 2.7 — Verify setup

```bash
# Start the API
make minimal

# In another terminal, hit health endpoint
curl http://localhost:8000/api/v1/health
# Expected: {"status":"ok","app_name":"DeepTrade AI","mode":"paper",...}

curl http://localhost:8000/api/v1/health/ready
# Expected: {"ready":true,"checks":{"api":true,"db":true,"redis":true}}
```

If both return `true`, setup is complete.

---

## 3. Running the Application

You'll typically run **two processes** — backend API and frontend dev server.

### Option A — Local development (most common)

**Terminal 1 — Backend:**
```bash
make paper
# Starts FastAPI on http://localhost:8000 with hot reload
```

**Terminal 2 — Frontend:**
```bash
make frontend-dev
# Starts Vite dev server on http://localhost:5173
```

Open http://localhost:5173 in your browser. You should see DeepTrade AI dashboard.

### Option B — Full Docker stack

```bash
make up
# Starts everything in containers
```

Less convenient for development (no hot reload) but useful for verifying production-style deploy.

### Toggling Light/Dark Mode

In the bottom-left of the sidebar, three buttons let you switch between Light, Dark, and System (follows OS preference). Selection persists across sessions.

---

## 4. Daily Operations

### 4.1 — Daily Kite login (every trading day)

Kite Connect access tokens expire daily before market open (NSE compliance). You must regenerate the token each morning.

**Manual flow (recommended initially):**

1. Visit `http://localhost:8000/api/v1/auth/kite/login-url`
2. Click the URL returned — you'll be redirected to kite.zerodha.com
3. Login with your Zerodha credentials + 2FA
4. You'll be redirected to `/api/v1/auth/kite/callback?request_token=...`
5. The system automatically exchanges this for an access token and stores it in Redis (8-hour TTL)
6. Done — system is ready for the trading day

**Automated flow (set up once, optional):**

If you're comfortable storing credentials in a password manager:
- Use `scripts/daily_kite_login.py` (write this with Playwright)
- Schedule via cron at 06:00 IST: `0 6 * * 1-5 cd ~/deeptrade-ai && python scripts/daily_kite_login.py`

### 4.2 — Pre-market (before 09:15 IST)

```bash
# Check system health
curl http://localhost:8000/api/v1/health/ready

# Verify Kite connection
curl http://localhost:8000/api/v1/health
# Mode should show "paper" or "live"
```

### 4.3 — During market hours (09:15 - 15:30 IST)

- **Watch the dashboard** at http://localhost:5173
- The system runs autonomously; paper trading happens automatically
- If `LIVE_TRADING_ENABLED=true`, live orders are also placed (with all risk gates)
- Monitor the **Open Positions** panel and **Today's P&L** stat
- The **Kill Switch** button (top right) halts all trading immediately if needed

### 4.4 — Post-market (after 15:30 IST)

- Review daily P&L on the **P&L** page
- Check **Compare** page for paper vs live divergence
- Review any **Risk Events** in the audit log
- Models retrain weekly automatically (see §5)

---

## 5. Model Training & Deployment

This is the most critical operational workflow. Models are **trained on Mac** (uses 18GB RAM efficiently) and **deployed to wherever the trading agent runs** (Mac during dev, VPS for live).

### 5.1 — Train initial models (one-time, takes ~2 hours)

```bash
# Train all 5 horizons (scalp, intraday, swing, weekly, monthly)
make train

# Or train one at a time:
python scripts/train_initial.py --horizon scalp
python scripts/train_initial.py --horizon swing
```

Output goes to `./models/<name>/<version>/`:
```
models/
└── meta_scalp/
    └── meta_scalp_1.0.0_2026-05-04/
        ├── model.lgb           # LightGBM booster
        ├── calibrator.pkl      # CalibratedClassifierCV
        ├── manifest.json       # metadata
        ├── features.json       # feature schema
        └── metrics.json        # training metrics
```

### 5.2 — Review training results

After training, the script prints metrics. Check:

```
✓ meta_scalp v1.0.0_2026-05-04
    Composite score: 0.62      ← must be ≥ 0.55
    Path: ./models/meta_scalp/meta_scalp_1.0.0_2026-05-04
```

**Acceptance criteria** (from v7 §EE):
- Composite score ≥ 0.55 (rejects models with insufficient quality)
- AUC OOS ≥ 0.55 (scalp), 0.58 (monthly)
- Profit factor ≥ 1.30
- Cost-shock test: must still pass at 1.5× costs
- Deflated Sharpe ≥ 0.80

If a model fails, **don't activate it.** Either:
- Add more features and retrain
- Accept that this strategy doesn't work yet
- Try a different strategy

### 5.3 — Deploy a trained model

After confirming metrics pass, register the model in the database:

```bash
make deploy-model name=meta_scalp version=1.0.0_2026-05-04
```

This:
1. Reads the artifact from `./models/<name>/<version>/`
2. Registers in `model_registry` table with state=`CANDIDATE`
3. Optionally rsyncs to VPS if `--target=vps` flag used

For VPS deployment (when running live):
```bash
python scripts/deploy_model.py \
  --name meta_scalp \
  --version 1.0.0_2026-05-04 \
  --target vps \
  --vps-host user@your-vps-ip
```

### 5.4 — Activate the deployed model

After deployment, the model is in CANDIDATE state. To put it into production:

**Via UI (recommended):**
1. Open http://localhost:5173/models
2. Find your model in the list (state=CANDIDATE)
3. Click **Activate**
4. Currently active model auto-deactivates; new one becomes ACTIVE

**Via API:**
```bash
curl -X POST http://localhost:8000/api/v1/models/meta_scalp/1.0.0_2026-05-04/activate
```

The system immediately starts using the new model for signal generation.

### 5.5 — Weekly model checks (automatic)

Every Monday at 06:00 IST, `scripts/weekly_check.py` runs:

1. Pulls last 7 days of model predictions vs actuals
2. Computes quality metrics (AUC, profit factor, Sortino)
3. **If above floor:** keep current model (no action)
4. **If below floor + drift detected:** trigger fine-tune (warm-start)
5. **If severely degraded:** trigger full retrain

Set up the cron:
```bash
crontab -e
# Add this line:
0 6 * * 1 cd ~/deeptrade-ai && /path/to/python scripts/weekly_check.py
```

### 5.6 — Manual rollback

If a newly activated model misbehaves:

**Via UI:** Models page → click rollback icon next to active model.
**Via API:** `curl -X POST http://localhost:8000/api/v1/models/meta_scalp/rollback`

Previous version is reactivated immediately.

---

## 6. Going Live (When Ready)

**Do not skip this section.** Going live before paper validation is the #1 cause of retail algo losses.

### 6.1 — Paper validation (60 days minimum)

Before enabling live, the system MUST run for 60 calendar days in paper mode and meet acceptance criteria:

| Metric | Target |
|---|---|
| Number of trades | ≥ 50 |
| Sharpe ratio | ≥ 1.0 |
| Profit factor | ≥ 1.3 |
| Max drawdown | ≤ 15% |
| Hit rate | ≥ 45% |
| Cost survival | profitable at 1.5× modeled costs |

Check progress on the **P&L** page after 60 days. If criteria not met, **don't go live.** Either extend paper, add features, or retire the strategy.

### 6.2 — Provision static IP (required for live)

NSE/SEBI requires API order placement from a registered static IP. Three options:

**Option A — Hostinger VPS (recommended):**
1. Sign up at hostinger.com → KVM 2 plan, **Mumbai data center**
2. After provisioning, note the static IPv4
3. SSH in: `ssh root@your-vps-ip`
4. Install Docker + clone repo + run `make setup`

**Option B — ISP static IP:**
- Contact your ISP (Airtel/Jio Business/ACT) for a static IP plan
- Cost: ₹500-2000/month additional
- Trade from Mac at home only

**Option C — Cloud VPN with dedicated IP:**
- Less reliable; not recommended

### 6.3 — Whitelist static IP with Zerodha

1. Login to https://developers.kite.trade/apps
2. Edit your app
3. In "Whitelisted IPs" field, enter your static IP
4. Save
5. Wait 15-30 min for activation

### 6.4 — Enable live trading

Once paper validation passes AND static IP is whitelisted:

1. **In `.env` on the VPS** (NOT your Mac):
   ```bash
   LIVE_TRADING_ENABLED=true
   MODE=live
   ```
2. **Restart the API** on the VPS:
   ```bash
   docker compose restart api
   ```
3. **In the UI** (http://your-vps-ip:8000 or via reverse proxy):
   - Go to **Auto Scalping** page
   - Configure your limits:
     - Max total trades: start small (e.g., 20)
     - Max per day: 5-10
     - Per-trade capital cap: ₹2,000-5,000
     - Total capital at risk: ₹15,000
   - Type `ENABLE_LIVE` in the confirmation box
   - Click **Enable Auto Scalping**
4. Live orders now flow through Kite

### 6.5 — Probe phase (15-20 days)

For the first 15-20 trading days of live, keep limits very small. The goal is to:
- Verify live execution matches paper (latency, slippage, fills)
- Catch any bugs before they're expensive
- Validate the paper-to-live correlation

Acceptance criteria for probe phase:
- Paper-vs-live correlation > 0.7 (Compare page)
- Live results within 1 standard deviation of paper expected
- No risk events (HALT severity)
- All limits respected

If probe fails, return to paper. Don't scale up.

### 6.6 — Cautious live (ongoing)

After probe passes, you can gradually raise UI limits as desired. Continue to:
- Review weekly P&L every Sunday
- Check model drift via Models page
- Watch for paper-vs-live divergence on Compare page
- Be ready to disable auto-scalping if performance degrades

---

## 7. Troubleshooting

### "Database connection refused"

```bash
docker compose ps
# If postgres isn't running:
docker compose up -d postgres
sleep 10
make migrate
```

### "Kite session expired"

Daily login required. Visit `/api/v1/auth/kite/login-url` and re-authenticate.

### "TimescaleDB extension not found"

```bash
docker compose exec postgres psql -U deeptrade -d deeptrade -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
```

### Frontend shows blank page

- Open browser DevTools Console
- Check if API is reachable: `curl http://localhost:8000/api/v1/health`
- Verify CORS in `.env`: `CORS_ORIGINS=http://localhost:5173`

### Model training is slow

- Check Activity Monitor — Python should be using ~12-15GB RAM
- If using less, increase `n_estimators` and feature count
- Each horizon takes 15-45 min on M3 Pro 18GB

### Paper P&L diverges from expected

- Check fee model in `core/brokers/zerodha/cost_model.py`
- Verify slippage settings in `core/brokers/paper/adapter.py`
- Recent NSE charge updates may need cost model adjustment

### "Order rejected: insufficient broker balance"

The risk engine blocks live orders when broker balance < your-set-buffer. This is by design.
- Check actual Zerodha balance via Kite app
- Lower the `broker_balance_min_buffer` in auto-scalping settings
- Or transfer more funds to Zerodha

### Live order rejected with "static IP not whitelisted"

- Confirm your VPS IP matches what's in Kite Connect dashboard
- Note IP changes are limited to once per week
- May need to wait 30 min after IP change for propagation

---

## 8. File & Directory Reference

```
deeptrade-ai/
│
├── README.md                    # Project overview
├── RUN_GUIDE.md                 # This file
├── pyproject.toml               # Python project config
├── docker-compose.yaml          # Service definitions
├── Dockerfile                   # API container
├── Makefile                     # One-command operations
├── alembic.ini                  # Migration config
├── .env.example                 # Environment template
│
├── apps/                        # Application entry points
│   └── api/                     # FastAPI server
│       ├── main.py              # App factory
│       ├── routers/             # HTTP endpoints
│       └── streams/             # SSE streams
│
├── core/                        # Shared libraries
│   ├── config.py                # Settings singleton
│   ├── models/                  # Pydantic models (Bar, Signal, Order, ...)
│   ├── db/                      # SQLAlchemy ORM + engine
│   ├── brokers/                 # Broker adapters
│   │   ├── base.py              # Adapter Protocol
│   │   ├── zerodha/             # Zerodha implementation
│   │   └── paper/               # Paper sim engine
│   ├── strategies/              # Trading strategies
│   │   ├── orb.py               # Opening Range Breakout
│   │   ├── connors_rsi.py       # 2-RSI mean reversion
│   │   ├── fake_breakout_filter.py  # 8-layer filter (v7 §DD)
│   │   └── loader.py            # YAML loader
│   ├── risk/                    # Risk engine + order router
│   └── ml/                      # Training, registry, metrics
│
├── strategies/                  # Strategy YAML configs
│   ├── orb_nifty_scalp.yaml
│   └── connors_rsi_swing.yaml
│
├── db/migrations/               # Alembic migrations
│   └── versions/0001_initial.py
│
├── frontend/                    # React UI
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js       # White/black/grey palette
│   └── src/
│       ├── App.tsx              # Routes
│       ├── components/Layout.tsx  # Sidebar + header
│       ├── pages/               # All UI pages
│       ├── api/client.ts        # Backend API wrapper
│       ├── stores/theme.ts      # Light/dark mode
│       └── lib/utils.ts         # cn(), formatINR(), etc.
│
├── scripts/                     # Operational scripts
│   ├── train_initial.py         # Initial model training
│   └── deploy_model.py          # Register & rsync models
│
├── tests/                       # Pytest tests
│
├── deploy/                      # Deploy artifacts
│   └── init-db.sql              # TimescaleDB extension setup
│
├── models/                      # Trained model artifacts (gitignored)
│   └── meta_scalp/<version>/
│
└── data/                        # Local data store (gitignored)
    └── features/                # Parquet feature store
```

---

## Quick Command Reference

```bash
# Setup
make install              # Install Python deps
make setup                # Full setup (deps + DB + migrate)

# Development
make paper                # Run API in paper mode
make frontend-dev         # Run React dev server
make migrate              # Apply DB migrations

# Training
make train                # Train all 5 model horizons
make weekly-check         # Manual weekly model check
make deploy-model name=meta_scalp version=1.0.0_2026-05-04

# Docker
make up                   # Start all services
make down                 # Stop all services
make logs                 # Tail logs

# Testing
make test                 # Run pytest
make lint                 # ruff + mypy
make format               # Format code

# Database operations
alembic revision --autogenerate -m "description"  # New migration
alembic upgrade head                              # Apply migrations
alembic downgrade -1                              # Rollback one
```

---

## Honest Notes

- **First month is the hardest.** Daily Kite login, paper trading, watching results — it's tedious but essential.
- **Don't skip paper validation.** 60 days isn't optional. Markets change; what worked in backtest may not work today.
- **Most strategies will fail.** Of the three (ORB, Connors, PEAD), expect 1-2 to pass live validation. That's normal.
- **Realistic expectations:** Sharpe 0.8-1.4, CAGR 10-20%, drawdown 10-18%. If your numbers look better, suspect overfitting.
- **The system is a tool, not a money machine.** Discipline, regime awareness, and the courage to retire failing strategies are what make it work.

Good luck.
