"""Bar-level backtest — simulates trades from trained LightGBM models on historical data.

Approach:
  - Entry: signal bar close (model predicts prob > threshold after bar closes)
  - Hold:  N bars from SCALP_TARGETS (5 for 1m, 3 for 15m, 5 for swing)
  - Exit:  forward close at bar T+N
  - Cost:  0.06% round-trip (NSE brokerage + STT + exchange + GST + stamp duty)
  - Sizing: fixed % of capital per trade (configurable)

Output per model (saved to ./backtests/<model>/<YYYYMMDD_HHMMSS>/):
  trades.csv       — per-trade log with entry time, return, P&L
  equity_curve.csv — capital value at each trade exit
  metrics.json     — summary statistics

Usage:
    python scripts/backtest.py                           # all models, last 6 months
    python scripts/backtest.py --model scalp_15m
    python scripts/backtest.py --from-date 2025-01-01 --to-date 2026-01-01
    python scripts/backtest.py --capital 500000 --position-pct 0.05
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from core.ml import load_model_artifact
from core.ml.features import (
    SCALP_FEATURE_COLS,
    SWING_FEATURE_COLS,
    build_scalp_dataset_async,
    build_swing_dataset_async,
)

logger = structlog.get_logger(__name__)

_COST_PCT = 0.0006  # 0.06% round-trip (NSE realistic estimate)

# ── Symbol universes (same as train_initial.py) ───────────────────────────────

_INDEX_SYMBOLS = ["NIFTY 50", "NIFTY BANK"]

_NIFTY_50 = [
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
_NIFTY_NEXT_50 = [
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
_NIFTY_100 = _NIFTY_50 + _NIFTY_NEXT_50

# ── Model registry ────────────────────────────────────────────────────────────

MODEL_META: dict[str, dict[str, Any]] = {
    "scalp_1m": {
        "mode": "scalp",
        "symbols": _INDEX_SYMBOLS,
        "exchange": "NSE",
        "timeframe": "1m",
        "feature_cols": SCALP_FEATURE_COLS,
        "entry_threshold": 0.55,
        "position_pct": 0.10,
        "lookback_months": 48,   # 4 years
    },
    "scalp_15m": {
        "mode": "scalp",
        "symbols": _INDEX_SYMBOLS,
        "exchange": "NSE",
        "timeframe": "15m",
        "feature_cols": SCALP_FEATURE_COLS,
        "entry_threshold": 0.50,
        "position_pct": 0.10,
        "lookback_months": 48,
    },
    "swing_1d": {
        "mode": "swing",
        "symbols": _NIFTY_100,
        "exchange": "NSE",
        "timeframe": "1d",
        "feature_cols": SWING_FEATURE_COLS,
        "entry_threshold": 0.42,
        "position_pct": 0.05,
        "lookback_months": 48,
    },
    # Longer-hold strategies — train with: make train model=momentum_15m intraday_1h
    "momentum_15m": {
        "mode": "scalp",
        "symbols": _INDEX_SYMBOLS,
        "exchange": "NSE",
        "timeframe": "15m",
        "feature_cols": SCALP_FEATURE_COLS,
        "entry_threshold": 0.52,
        "position_pct": 0.12,
        "lookback_months": 48,
        "forward_bars":    6,         # 90-min hold target
        "label_threshold": 0.005,     # 0.5% minimum move
    },
    "intraday_1h": {
        "mode": "scalp",
        "symbols": _INDEX_SYMBOLS,
        "exchange": "NSE",
        "timeframe": "1h",
        "feature_cols": SCALP_FEATURE_COLS,
        "entry_threshold": 0.52,
        "position_pct": 0.15,
        "lookback_months": 48,
        "forward_bars":    3,         # 3-hour hold target
        "label_threshold": 0.006,     # 0.6% minimum move
    },
}


# ── Data loading ──────────────────────────────────────────────────────────────

async def _load_all(
    configs: dict[str, dict[str, Any]],
    from_dt: datetime,
    to_dt: datetime,
) -> dict[str, pd.DataFrame]:
    """Load feature datasets in a single event loop."""
    results: dict[str, pd.DataFrame] = {}
    for name, meta in configs.items():
        if meta["mode"] == "scalp":
            df = await build_scalp_dataset_async(
                meta["symbols"], meta["exchange"], meta["timeframe"], from_dt, to_dt,
                forward_bars=meta.get("forward_bars"),
                label_threshold=meta.get("label_threshold"),
            )
        else:
            df = await build_swing_dataset_async(
                meta["symbols"], meta["exchange"], from_dt, to_dt,
                forward_bars=meta.get("forward_bars"),
                label_threshold=meta.get("label_threshold"),
            )
        results[name] = df
        logger.info("data_loaded", name=name, rows=len(df))
    return results


# ── Artifact discovery ────────────────────────────────────────────────────────

def _find_latest(models_dir: Path, name: str) -> Path | None:
    root = models_dir / name
    if not root.exists():
        return None
    versions = [d for d in root.iterdir() if d.is_dir() and (d / "manifest.json").exists()]
    return max(versions, key=lambda d: d.stat().st_mtime) if versions else None


# ── Trade simulation ──────────────────────────────────────────────────────────

def _simulate(
    df: pd.DataFrame,
    artifact: Any,
    feature_cols: list[str],
    entry_threshold: float,
    position_pct: float,
    initial_capital: float,
    cost_pct: float = _COST_PCT,
    leverage: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Simulate trades with compound position sizing and optional leverage.

    Leverage multiplies both gains and losses — use to model NIFTY/BANKNIFTY
    futures (typically 3-7× intraday) or options equivalent exposure.
    Position sizing compounds: each trade uses position_pct of *current* equity,
    not of the fixed initial capital.
    """
    available = [c for c in feature_cols if c in df.columns]
    if not available or "fwd_return" not in df.columns:
        return pd.DataFrame(), {}

    X = df[available].values
    raw_probs = artifact.booster.predict(X)
    probs     = artifact.calibrator.predict(raw_probs) if artifact.calibrator else raw_probs

    signals = df.copy()
    signals["prob"] = probs
    signals = signals[signals["prob"] > entry_threshold].copy()

    if signals.empty:
        return pd.DataFrame(), {"n_trades": 0}

    signals["gross_return"] = signals["fwd_return"]
    # net_return includes cost and leverage — this is the per-position return
    signals["net_return"] = (signals["gross_return"] - cost_pct) * leverage

    # Compound position sizing: each trade is sized on current equity
    signals = signals.sort_values("time").reset_index(drop=True)
    equity   = initial_capital
    pos_vals = []
    pnls     = []
    equities = []
    for nr in signals["net_return"]:
        pos_val = equity * position_pct
        pnl     = pos_val * nr
        equity  = max(equity + pnl, 1.0)   # floor at 1 to avoid sign flip
        pos_vals.append(pos_val)
        pnls.append(pnl)
        equities.append(equity)

    signals["position_val"] = pos_vals
    signals["pnl"]          = pnls
    signals["equity"]       = equities
    signals["win"]          = (signals["net_return"] > 0).astype(int)

    ret = signals["net_return"].values
    wins   = ret[ret > 0]
    losses = ret[ret < 0]

    n             = len(ret)
    win_rate      = len(wins) / n if n > 0 else 0.0
    gross_profit  = float(wins.sum())         if len(wins)   > 0 else 0.0
    gross_loss    = float(abs(losses.sum()))  if len(losses) > 0 else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss  > 0 else 0.0
    expectancy    = float(ret.mean())

    if ret.std() > 0:
        sharpe = float(ret.mean() / ret.std()) * math.sqrt(252)
    else:
        sharpe = 0.0

    downside = ret[ret < 0]
    if len(downside) > 0 and downside.std() > 0:
        sortino = float(ret.mean() / downside.std()) * math.sqrt(252)
    else:
        sortino = 0.0

    equity_arr = signals["equity"].values
    peak       = np.maximum.accumulate(equity_arr)
    drawdown   = (peak - equity_arr) / peak
    max_dd     = float(drawdown.max()) if len(drawdown) > 0 else 0.0

    total_ret     = (signals["equity"].iloc[-1] - initial_capital) / initial_capital
    final_capital = float(signals["equity"].iloc[-1])

    metrics: dict[str, Any] = {
        "n_trades":        n,
        "win_rate":        round(win_rate, 4),
        "profit_factor":   round(profit_factor, 4),
        "expectancy_pct":  round(expectancy * 100, 4),
        "sharpe":          round(sharpe, 4),
        "sortino":         round(sortino, 4),
        "max_drawdown":    round(max_dd, 4),
        "total_return":    round(total_ret, 4),
        "initial_capital": initial_capital,
        "final_capital":   round(final_capital, 2),
        "total_pnl":       round(final_capital - initial_capital, 2),
        "cost_pct":        cost_pct,
        "leverage":        leverage,
        "entry_threshold": entry_threshold,
    }

    trades_df = signals[[
        "time", "symbol", "prob", "label",
        "gross_return", "net_return", "pnl", "win", "equity",
    ]].copy()

    return trades_df, metrics


def _period_analysis(
    trades_df: pd.DataFrame,
    to_dt: datetime,
) -> list[tuple[str, int, float, float]]:
    """Per-period profit factor for trailing 1m/3m/6m/12m windows.

    Returns list of (label, n_trades, profit_factor, win_pct).
    Uses net_return column (already cost-adjusted in _simulate).
    """
    if trades_df.empty:
        return []

    trades = trades_df.copy()
    trades["time"] = pd.to_datetime(trades["time"], utc=True)
    to_ts = pd.Timestamp(to_dt).tz_localize("UTC") if to_dt.tzinfo is None else pd.Timestamp(to_dt)

    rows: list[tuple[str, int, float, float]] = []
    for label, days in [("1m", 30), ("3m", 90), ("6m", 180), ("12m", 365)]:
        cutoff = to_ts - timedelta(days=days)
        w = trades[trades["time"] >= cutoff]
        n = len(w)
        if n == 0:
            rows.append((label, 0, float("nan"), float("nan")))
            continue
        ret = w["net_return"].values
        wins   = ret[ret > 0]
        losses = ret[ret < 0]
        gp = float(wins.sum())       if len(wins)   > 0 else 0.0
        gl = float(abs(losses.sum())) if len(losses) > 0 else 0.0
        pf  = round(gp / gl, 3) if gl > 0 else 0.0
        wrt = round(len(wins) / n * 100, 1)
        rows.append((label, n, pf, wrt))
    return rows


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Bar-level backtest for DeepTrade AI models")
    parser.add_argument(
        "--model", choices=list(MODEL_META) + ["all"], default="all",
        help="Which model to backtest (default: all)",
    )
    parser.add_argument("--from-date", default="",
                        help="Start date YYYY-MM-DD (default: lookback from today)")
    parser.add_argument("--to-date", default=str(date.today()),
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--capital", type=float, default=1_000_000,
                        help="Initial capital in INR (default: 10,00,000)")
    parser.add_argument("--position-pct", type=float, default=0.0,
                        help="Override position size as fraction of capital (0 = use per-model default)")
    parser.add_argument("--leverage", type=float, default=1.0,
                        help="Leverage multiplier, e.g. 5.0 for NIFTY futures MIS (default: 1.0 = equity)")
    parser.add_argument("--models-dir", default="./models")
    parser.add_argument("--output-dir", default="./backtests")
    args = parser.parse_args()

    models_dir = Path(args.models_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    configs: dict[str, dict[str, Any]] = (
        MODEL_META if args.model == "all"
        else {args.model: MODEL_META[args.model]}
    )

    # Build date range
    to_dt = datetime(
        *map(int, args.to_date.split("-")), 23, 59, 59, tzinfo=timezone.utc
    )
    if args.from_date:
        from_dt = datetime(*map(int, args.from_date.split("-")), tzinfo=timezone.utc)
    else:
        # Use the widest lookback among selected models
        max_months = max(m["lookback_months"] for m in configs.values())
        from_dt = to_dt - timedelta(days=max_months * 30)

    leverage_label = f"{args.leverage:.1f}×" if args.leverage != 1.0 else "1× (equity, no leverage)"
    print(f"\nBacktest period: {from_dt.date()} → {to_dt.date()}")
    print(f"Capital: ₹{args.capital:,.0f}  |  Leverage: {leverage_label}  |  Models: {list(configs)}\n")

    # Load all datasets in one event loop
    logger.info("loading_datasets", models=list(configs))
    datasets = asyncio.run(_load_all(configs, from_dt, to_dt))

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print(f"{'Model':<16} {'Trades':>7} {'Win%':>6} {'PF':>6} {'Sharpe':>7} "
          f"{'MaxDD':>7} {'Return':>8} {'P&L (₹)':>12}")
    print("=" * 70)

    all_results: list[dict[str, Any]] = []

    for name, meta in configs.items():
        df = datasets[name]

        artifact_path = _find_latest(models_dir, name)
        if artifact_path is None:
            print(f"  {name:<14}: NO MODEL — run make train first")
            continue

        artifact = load_model_artifact(artifact_path)
        if artifact.booster is None:
            print(f"  {name:<14}: BOOSTER MISSING at {artifact_path}")
            continue

        if df.empty:
            print(f"  {name:<14}: NO DATA for this period")
            continue

        pos_pct = args.position_pct if args.position_pct > 0 else meta["position_pct"]
        feature_cols = [c for c in meta["feature_cols"] if c in df.columns]

        trades_df, metrics = _simulate(
            df, artifact, feature_cols,
            entry_threshold=meta["entry_threshold"],
            position_pct=pos_pct,
            initial_capital=args.capital,
            leverage=args.leverage,
        )

        n          = metrics.get("n_trades", 0)
        win_pct    = metrics.get("win_rate", 0) * 100
        pf         = metrics.get("profit_factor", 0)
        sharpe     = metrics.get("sharpe", 0)
        max_dd     = metrics.get("max_drawdown", 0) * 100
        total_ret  = metrics.get("total_return", 0) * 100
        total_pnl  = metrics.get("total_pnl", 0)

        print(
            f"  {name:<14} {n:>7,} {win_pct:>5.1f}% {pf:>6.2f} {sharpe:>7.2f} "
            f"{max_dd:>6.1f}% {total_ret:>+7.1f}% {total_pnl:>+12,.0f}"
        )
        print(f"    model: {artifact_path.name}  |  data: {len(df):,} bars"
              f"  ({df['time'].min().date()} → {df['time'].max().date()})")

        # Period-by-period profit factor analysis
        period_rows = _period_analysis(trades_df, to_dt)
        if period_rows:
            parts = [
                f"{lbl}: PF={pf:.2f} ({n} trades, {wp:.1f}%)"
                if not math.isnan(pf) else f"{lbl}: —"
                for lbl, n, pf, wp in period_rows
            ]
            print(f"    Trailing PF  →  " + "  |  ".join(parts))

        # Save outputs
        model_out = output_dir / name / run_ts
        model_out.mkdir(parents=True, exist_ok=True)

        if not trades_df.empty:
            trades_df.to_csv(model_out / "trades.csv", index=False)

            equity = trades_df[["time", "equity"]].copy()
            equity.to_csv(model_out / "equity_curve.csv", index=False)

        metrics["model_version"] = artifact_path.name
        metrics["backtest_from"] = str(from_dt.date())
        metrics["backtest_to"]   = str(to_dt.date())
        (model_out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))

        all_results.append({"name": name, "metrics": metrics, "path": str(model_out)})

    print("=" * 70)

    if all_results:
        print(f"\nOutputs saved to: {output_dir}/")
        for r in all_results:
            print(f"  {r['name']}: {r['path']}")
    print()


if __name__ == "__main__":
    main()
