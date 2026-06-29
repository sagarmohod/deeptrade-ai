# DeepTrade AI — Makefile
.PHONY: help install setup up down logs test lint format migrate kite-login \
        fetch-data fetch-data-dry fetch-4yr \
        fetch-indices fetch-nifty fetch-banknifty fetch-vix \
        fetch-equity fetch-nifty50 fetch-nifty100 \
        train weekly-check backtest backtest-long backtest-levered ab-test \
        deploy-model paper minimal frontend-install frontend-dev clean

help:
	@echo "DeepTrade AI — Available commands:"
	@echo ""
	@echo "  make install         Install Python deps (uv)"
	@echo "  make setup           Initial setup (install + DBs + migrate)"
	@echo "  make up              Start all services (Docker)"
	@echo "  make down            Stop all services"
	@echo "  make logs            Tail Docker logs"
	@echo ""
	@echo "  make migrate         Run Alembic migrations"
	@echo "  make migration name=<x>  Create new migration"
	@echo ""
	@echo "  make paper           Start paper trading engine"
	@echo "  make minimal         Start minimal API only (no workers)"
	@echo ""
	@echo "  make kite-login       Daily Zerodha OAuth login (saves token to .env)"
	@echo "  make fetch-data       Fetch everything (indices + equities)"
	@echo "  make fetch-data-dry   Dry-run: print fetch plan, no API calls"
	@echo "  --- Indices (2018-present) ---"
	@echo "  make fetch-indices    All indices (NIFTY + BANKNIFTY + VIX)"
	@echo "  make fetch-nifty      NIFTY 50 index only"
	@echo "  make fetch-banknifty  NIFTY BANK index only"
	@echo "  make fetch-vix        India VIX only"
	@echo "  --- Equities ---"
	@echo "  make fetch-nifty50    Nifty 50 equities (15m/1h/1d)"
	@echo "  make fetch-nifty100   Nifty Next 50 equities (1d only)"
	@echo ""
	@echo "  make train           Train initial models (M3 Pro local)"
	@echo "  make weekly-check    Run weekly model check"
	@echo "  make backtest           Bar-level backtest all models (equity, no leverage)"
	@echo "  make backtest-long      4-year backtest from 2022-01-01"
	@echo "  make backtest-levered   4-year backtest at 5× leverage (futures sim)"
	@echo "  make ab-test            All strategies, 4-year, 5× leverage (A/B compare)"
	@echo "  make backtest model=scalp_1m   Single model"
	@echo "  make deploy-model name=<x> version=<y>"
	@echo ""
	@echo "  make frontend-install   Install React deps"
	@echo "  make frontend-dev       Start Vite dev server"
	@echo ""
	@echo "  make test            Run tests"
	@echo "  make lint            Run ruff + mypy"
	@echo "  make format          Format code"
	@echo "  make clean           Remove build artifacts"

# ---------- Setup ----------

install:
	pip install uv
	uv pip install -e ".[dev]"

setup: install
	docker compose up -d postgres redis qdrant
	@sleep 5
	$(MAKE) migrate
	@echo ""
	@echo "Setup complete. Next steps:"
	@echo "  1. Copy .env.example to .env and fill in your Kite API keys"
	@echo "  2. Run 'make paper' to start paper trading"
	@echo "  3. In another terminal: 'make frontend-dev'"

# ---------- Docker ----------

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

# ---------- Database ----------

migrate:
	alembic upgrade head

migration:
	@if [ -z "$(name)" ]; then echo "Usage: make migration name=<name>"; exit 1; fi
	alembic revision --autogenerate -m "$(name)"

# ---------- Run Modes ----------

minimal:
	uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

paper:
	@echo "Starting DeepTrade AI in PAPER mode..."
	MODE=paper uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

# ---------- Data ----------

kite-login:
	@echo "Opening Zerodha login in browser — log in and the token is saved automatically."
	python scripts/kite_login.py

# ── All data ──────────────────────────────────────────────────────────
fetch-data:
	python scripts/fetch_historical.py --preset all

fetch-data-dry:
	python scripts/fetch_historical.py --preset all --dry-run

# ── Indices (2018 → today) ────────────────────────────────────────────
fetch-indices:
	python scripts/fetch_historical.py --preset indices

fetch-nifty:
	python scripts/fetch_historical.py --preset indices --index-filter "NIFTY 50"

fetch-banknifty:
	python scripts/fetch_historical.py --preset indices --index-filter "NIFTY BANK"

fetch-vix:
	python scripts/fetch_historical.py --preset indices --index-filter "INDIA VIX"

# ── Equities ──────────────────────────────────────────────────────────
fetch-nifty50:
	python scripts/fetch_historical.py --preset nifty50

fetch-nifty100:
	python scripts/fetch_historical.py --preset nifty100

# ---------- ML ----------

train:
	@echo "Training initial models (this runs on M3 Pro local)..."
	python scripts/train_initial.py

weekly-check:
	python scripts/weekly_check.py

backtest:
	@if [ -n "$(model)" ]; then \
		python scripts/backtest.py --model $(model) $(if $(from),--from-date $(from),) $(if $(to),--to-date $(to),) $(if $(capital),--capital $(capital),) $(if $(leverage),--leverage $(leverage),); \
	else \
		python scripts/backtest.py $(if $(from),--from-date $(from),) $(if $(to),--to-date $(to),) $(if $(capital),--capital $(capital),) $(if $(leverage),--leverage $(leverage),); \
	fi

backtest-long:
	python scripts/backtest.py --from-date 2022-01-01 $(if $(model),--model $(model),) $(if $(capital),--capital $(capital),)

backtest-levered:
	python scripts/backtest.py --from-date 2022-01-01 --leverage 5.0 $(if $(model),--model $(model),) $(if $(capital),--capital $(capital),)

ab-test:
	@echo "=== A/B test: all strategies, 4-year window, 5× leverage ==="
	python scripts/backtest.py --from-date 2022-01-01 --leverage 5.0

fetch-4yr:
	@echo "Fetching 4 years of historical data (2021-01-01 → today)..."
	python scripts/fetch_historical.py --preset all --from-date 2021-01-01

deploy-model:
	@if [ -z "$(name)" ] || [ -z "$(version)" ]; then \
		echo "Usage: make deploy-model name=<x> version=<y>"; exit 1; \
	fi
	python scripts/deploy_model.py --name $(name) --version $(version)

# ---------- Frontend ----------

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

# ---------- Testing & Quality ----------

test:
	pytest tests/ -v

lint:
	ruff check .
	mypy core apps

format:
	ruff format .
	ruff check --fix .

# ---------- Cleanup ----------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
