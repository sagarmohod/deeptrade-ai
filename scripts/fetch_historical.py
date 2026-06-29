"""Fetch Zerodha historical OHLCV data and store in market_bars.

Presets:
  indices   — NIFTY 50 + BANKNIFTY (1m/5m/15m/1h/1d) + India VIX (1d)  [from 2018]
  nifty50   — Nifty 50 equities (15m/1h/1d)
  nifty100  — Nifty 100 equities (1d only)
  all       — All of the above (default)

Usage:
    python scripts/fetch_historical.py --preset indices
    python scripts/fetch_historical.py --preset indices --index-filter "NIFTY 50"
    python scripts/fetch_historical.py --preset nifty50
    python scripts/fetch_historical.py --symbols RELIANCE,TCS --timeframes 1d,1h
    python scripts/fetch_historical.py --dry-run

Logs are written to logs/fetch_YYYYMMDD_HHMMSS.log automatically.
Requires KITE_ACCESS_TOKEN in .env (run: make kite-login first).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import structlog

from core.brokers.zerodha.adapter import ZerodhaAdapter
from core.data.fetcher import KNOWN_TOKENS, ZerodhaHistoricalFetcher
from core.db.engine import close_engine, get_session_factory

INDEX_FROM_DATE = date(2018, 1, 1)
EQUITY_FROM_DATE_DEFAULT = date.today() - timedelta(days=730)


# ─────────────────────────────────────────────────────────────────────
# File logging setup — call once at startup
# ─────────────────────────────────────────────────────────────────────

def _setup_logging() -> Path:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"fetch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    # Plain text format for the log file
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    # Route structlog through stdlib so the file handler receives it too
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    return log_path


# ─────────────────────────────────────────────────────────────────────
# Symbol universes
# ─────────────────────────────────────────────────────────────────────

INDICES = [
    ("NIFTY 50",   KNOWN_TOKENS["NIFTY 50"],   ["1m", "5m", "15m", "1h", "1d"]),
    ("NIFTY BANK", KNOWN_TOKENS["NIFTY BANK"], ["1m", "5m", "15m", "1h", "1d"]),
    ("INDIA VIX",  KNOWN_TOKENS["INDIA VIX"],  ["1d"]),
]

NIFTY_50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BHARTIARTL", "BPCL",
    "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
    "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBIN", "SBILIFE", "SHRIRAMFIN",
    "SUNPHARMA", "TATAMOTORS", "TATASTEEL", "TATACONSUM", "TECHM",
    "TITAN", "ULTRACEMCO", "UPL", "WIPRO", "TCS",
]

NIFTY_NEXT_50 = [
    "ABB", "ADANIGREEN", "ADANIPOWER", "AMBUJACEM", "AUROPHARMA",
    "BAJAJHLDNG", "BANKBARODA", "BERGEPAINT", "BOSCHLTD", "CANBK",
    "CHOLAFIN", "COLPAL", "DALBHARAT", "DABUR", "DLF",
    "GAIL", "GODREJCP", "GODREJPROP", "HAVELLS", "HDFCAMC",
    "HINDZINC", "ICICIGI", "ICICIPRULI", "INDUSTOWER", "IRCTC",
    "JINDALSTEL", "LTF", "LTIM", "LUPIN", "MARICO",
    "MCDOWELL-N", "MOTHERSON", "MPHASIS", "NAUKRI", "NMDC",
    "OFSS", "PAGEIND", "PIIND", "PNB", "RECLTD",
    "SAIL", "SBICARD", "SIEMENS", "SRF", "TATACOMM",
    "TATAPOWER", "TORNTPHARM", "TRENT", "VEDL", "ZOMATO",
]

NIFTY_100 = NIFTY_50 + NIFTY_NEXT_50

NIFTY50_TIMEFRAMES  = ["15m", "1h", "1d"]
NIFTY100_TIMEFRAMES = ["1d"]


# ─────────────────────────────────────────────────────────────────────
# Job descriptor
# ─────────────────────────────────────────────────────────────────────

@dataclass
class FetchJob:
    symbol: str
    timeframe: str
    from_date: date
    to_date: date
    token: int | None = None


def build_jobs(
    preset: str,
    to_date: date,
    equity_from: date,
    index_filter: str,
    custom_symbols: list[str],
    custom_tf: list[str],
    custom_from: date,
) -> list[FetchJob]:
    jobs: list[FetchJob] = []

    if custom_symbols:
        for sym in custom_symbols:
            for tf in custom_tf:
                jobs.append(FetchJob(symbol=sym, timeframe=tf, from_date=custom_from, to_date=to_date))
        return jobs

    if preset in ("indices", "all"):
        for name, token, timeframes in INDICES:
            if index_filter and name != index_filter:
                continue
            for tf in timeframes:
                jobs.append(FetchJob(symbol=name, timeframe=tf, from_date=INDEX_FROM_DATE, to_date=to_date, token=token))

    if preset in ("nifty50", "all"):
        for sym in NIFTY_50:
            for tf in NIFTY50_TIMEFRAMES:
                jobs.append(FetchJob(symbol=sym, timeframe=tf, from_date=equity_from, to_date=to_date))

    if preset in ("nifty100", "all"):
        seen = {(j.symbol, j.timeframe) for j in jobs if j.token is None}
        for sym in NIFTY_100:
            for tf in NIFTY100_TIMEFRAMES:
                if (sym, tf) not in seen:
                    jobs.append(FetchJob(symbol=sym, timeframe=tf, from_date=equity_from, to_date=to_date))

    return jobs


# ─────────────────────────────────────────────────────────────────────
# Fetch + store one job (incremental)
# ─────────────────────────────────────────────────────────────────────

def _short_error(e: Exception) -> str:
    """Return only the first line of an exception — avoids dumping full SQL params."""
    return str(e).split("\n")[0][:300]


async def run_job(job: FetchJob, fetcher: ZerodhaHistoricalFetcher, factory, exchange: str) -> int:
    async with factory() as session:
        latest = await fetcher.latest_bar_date(job.symbol, exchange, job.timeframe, session)

    effective_from = fetcher.resolve_from_date(latest, job.from_date)
    if effective_from is None:
        return 0

    if job.token is not None:
        bars = await fetcher.fetch_by_token(
            job.token, job.symbol, job.timeframe, effective_from, job.to_date, exchange
        )
    else:
        bars = await fetcher.fetch_symbol(
            job.symbol, job.timeframe, effective_from, job.to_date, exchange
        )

    async with factory() as session:
        new = await fetcher.upsert_bars(bars, session)
        await session.commit()

    return new


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

async def main() -> int:
    log_path = _setup_logging()
    logger = structlog.get_logger(__name__)
    logger.info("fetch_started", log_file=str(log_path))

    parser = argparse.ArgumentParser(description="Fetch Zerodha historical data")
    parser.add_argument("--preset", choices=["indices", "nifty50", "nifty100", "all"], default="all")
    parser.add_argument("--index-filter", default="",
                        help="Fetch only one index: 'NIFTY 50', 'NIFTY BANK', or 'INDIA VIX'")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--timeframes", default="")
    parser.add_argument("--equity-from", default=str(EQUITY_FROM_DATE_DEFAULT))
    parser.add_argument("--from-date", default="")
    parser.add_argument("--to-date", default=str(date.today()))
    parser.add_argument("--exchange", default="NSE")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    to_date     = date.fromisoformat(args.to_date)
    equity_from = date.fromisoformat(args.equity_from)
    custom_from = date.fromisoformat(args.from_date) if args.from_date else equity_from

    custom_symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    custom_tf      = [t.strip() for t in args.timeframes.split(",") if t.strip()] or ["1d"]

    jobs = build_jobs(args.preset, to_date, equity_from, args.index_filter,
                      custom_symbols, custom_tf, custom_from)

    by_symbol: dict[str, list[str]] = {}
    for j in jobs:
        by_symbol.setdefault(j.symbol, []).append(j.timeframe)

    if args.dry_run:
        print(f"Preset: {args.preset}  index-filter: '{args.index_filter}'  "
              f"{len(by_symbol)} symbols  {len(jobs)} jobs")
        for sym, tfs in by_symbol.items():
            print(f"  {sym:<25} {', '.join(tfs)}")
        return 0

    adapter = ZerodhaAdapter()
    try:
        await adapter.connect()
    except Exception as e:
        logger.error("zerodha_connect_failed", error=_short_error(e))
        return 1

    fetcher = ZerodhaHistoricalFetcher(adapter._kite)

    if any(j.token is None for j in jobs):
        try:
            await fetcher.load_instruments(args.exchange)
        except Exception as e:
            logger.error("instruments_load_failed", error=_short_error(e))
            return 1

        missing = sorted({j.symbol for j in jobs if j.token is None
                          and fetcher.get_token(j.symbol, args.exchange) is None})
        if missing:
            logger.warning("symbols_not_found", symbols=missing)
            skip = set(missing)
            jobs = [j for j in jobs if j.symbol not in skip]
            if not jobs:
                logger.error("no_valid_symbols")
                return 1

    factory   = get_session_factory()
    symbols   = list(dict.fromkeys(j.symbol for j in jobs))
    total_new = 0
    failed: list[str] = []

    for idx, sym in enumerate(symbols, 1):
        sym_jobs = [j for j in jobs if j.symbol == sym]
        sym_ok   = True

        for job in sym_jobs:
            try:
                new = await run_job(job, fetcher, factory, args.exchange)
                total_new += new
                logger.debug("job_ok", symbol=sym, timeframe=job.timeframe, new_rows=new)
            except Exception as e:
                # Only log the first line — avoids dumping full SQL + parameters
                logger.error("job_failed", symbol=sym, timeframe=job.timeframe,
                             error=_short_error(e))
                sym_ok = False
            finally:
                await asyncio.sleep(fetcher.RATE_LIMIT_SLEEP)

        logger.info("symbol_done", n=idx, total=len(symbols), symbol=sym,
                    status="ok" if sym_ok else "partial")
        if not sym_ok:
            failed.append(sym)

    await close_engine()
    logger.info("fetch_complete", total_new=total_new, symbols=len(symbols), failed=len(failed))
    if failed:
        logger.warning("failed_symbols", symbols=failed)

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
