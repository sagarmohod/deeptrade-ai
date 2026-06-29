"""Weekly model health check — re-evaluates all trained models on recent live data.

For each model in ./models/, loads the latest booster + calibrator, fetches recent
bars from the DB, computes out-of-sample metrics, and compares against quality floors.

Usage:
    python scripts/weekly_check.py              # check all models
    python scripts/weekly_check.py --model scalp_1m
    python scripts/weekly_check.py --models-dir ./models

Exit codes:
    0 — all checked models pass quality floor
    1 — one or more models fail or have no recent data (retraining recommended)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import structlog
from sklearn.metrics import roc_auc_score

from core.ml import (
    QualityMetrics,
    compute_composite_score,
    compute_metrics_from_trades,
    load_model_artifact,
)
from core.ml.features import (
    SCALP_FEATURE_COLS,
    SWING_FEATURE_COLS,
    build_scalp_dataset_async,
    build_swing_dataset_async,
)

logger = structlog.get_logger(__name__)

_ENTRY_THRESHOLD     = 0.55
_HIGH_CONF_THRESHOLD = 0.65
_COST_PCT            = 0.0006  # 0.06% round-trip — same as backtest.py

# ── Model registry ────────────────────────────────────────────────────────────

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

# lookback_weeks: how far back to pull data for the evaluation window
MODEL_META: dict[str, dict[str, Any]] = {
    "scalp_1m": {
        "mode": "scalp",
        "symbols": _INDEX_SYMBOLS,
        "exchange": "NSE",
        "timeframe": "1m",
        "feature_cols": SCALP_FEATURE_COLS,
        "lookback_weeks": 4,
        "entry_threshold": 0.55,
        "high_conf_threshold": 0.65,
    },
    "scalp_15m": {
        "mode": "scalp",
        "symbols": _INDEX_SYMBOLS,
        "exchange": "NSE",
        "timeframe": "15m",
        "feature_cols": SCALP_FEATURE_COLS,
        "lookback_weeks": 6,
        "entry_threshold": 0.50,  # label_rate ~17% → calibrated probs rarely hit 0.55
        "high_conf_threshold": 0.60,
    },
    "swing_1d": {
        "mode": "swing",
        "symbols": _NIFTY_100,
        "exchange": "NSE",
        "timeframe": "1d",
        "feature_cols": SWING_FEATURE_COLS,
        "lookback_weeks": 52,  # SMA200 needs 200 bars (~40 weeks warmup) + eval buffer
        "entry_threshold": 0.35,
        "high_conf_threshold": 0.45,
    },
}


# ── Data loading ──────────────────────────────────────────────────────────────

async def _load_all_recent(
    meta_map: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Fetch recent data for all models in a single event loop."""
    results: dict[str, Any] = {}
    now = datetime.now(timezone.utc)

    for name, meta in meta_map.items():
        start = now - timedelta(weeks=meta["lookback_weeks"])
        if meta["mode"] == "scalp":
            df = await build_scalp_dataset_async(
                meta["symbols"], meta["exchange"], meta["timeframe"], start, now
            )
        else:
            df = await build_swing_dataset_async(
                meta["symbols"], meta["exchange"], start, now
            )
        results[name] = df
        logger.info("recent_data_loaded", name=name, rows=len(df))

    return results


# ── Evaluation ────────────────────────────────────────────────────────────────

def _evaluate(
    artifact: Any,
    df: Any,
    feature_cols: list[str],
    entry_threshold: float = _ENTRY_THRESHOLD,
    high_conf_threshold: float = _HIGH_CONF_THRESHOLD,
    cost_pct: float = _COST_PCT,
) -> tuple[QualityMetrics, dict[str, Any]]:
    """Run model on recent data and return (QualityMetrics, prob_diagnostics)."""
    available = [c for c in feature_cols if c in df.columns]
    if len(available) < len(feature_cols):
        logger.warning("missing_features", count=len(set(feature_cols) - set(available)))

    X = df[available].values
    y = df["label"].values
    fwd = df["fwd_return"].values if "fwd_return" in df.columns else None

    raw_probs  = artifact.booster.predict(X)
    test_probs = artifact.calibrator.predict(raw_probs) if artifact.calibrator else raw_probs

    prob_diag: dict[str, Any] = {
        "max_prob":  round(float(test_probs.max()), 4),
        "p90_prob":  round(float(np.percentile(test_probs, 90)), 4),
        "mean_prob": round(float(test_probs.mean()), 4),
        "label_rate": round(float(y.mean()), 4),
    }

    try:
        auc = float(roc_auc_score(y, test_probs))
    except ValueError:
        auc = 0.5

    trade_mask = test_probs > entry_threshold
    n_above = int(trade_mask.sum())
    prob_diag["n_above_threshold"] = n_above

    if n_above < 5:
        m = QualityMetrics(auc=auc)
        m.composite_score = compute_composite_score(m)
        return m, prob_diag

    if fwd is not None:
        # Net returns after round-trip cost — consistent with backtest.py
        net_returns = (fwd[trade_mask] - cost_pct).tolist()
    else:
        net_returns = [(0.002 - cost_pct) if x == 1 else (-0.002 - cost_pct)
                       for x in y[trade_mask]]

    metrics = compute_metrics_from_trades(net_returns)
    metrics.auc = auc

    high_mask = test_probs > high_conf_threshold
    if high_mask.sum() > 5:
        metrics.precision_at_65 = float(y[high_mask].mean())

    metrics.brier_score = float(np.mean((test_probs - y) ** 2))
    metrics.composite_score = compute_composite_score(metrics)
    return metrics, prob_diag


# ── Artifact discovery ────────────────────────────────────────────────────────

def _find_latest(models_dir: Path, name: str) -> Path | None:
    """Return path to the most recently saved version directory for a model."""
    model_root = models_dir / name
    if not model_root.exists():
        return None
    versions = [
        d for d in model_root.iterdir()
        if d.is_dir() and (d / "manifest.json").exists()
    ]
    if not versions:
        return None
    return max(versions, key=lambda d: d.stat().st_mtime)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly model health check")
    parser.add_argument(
        "--model", choices=list(MODEL_META) + ["all"], default="all",
        help="Which model to check (default: all)",
    )
    parser.add_argument("--models-dir", default="./models",
                        help="Root directory containing saved models")
    args = parser.parse_args()

    models_dir = Path(args.models_dir)
    meta_map: dict[str, dict[str, Any]] = (
        MODEL_META if args.model == "all"
        else {args.model: MODEL_META[args.model]}
    )

    logger.info("weekly_check_started", models=list(meta_map))
    recent = asyncio.run(_load_all_recent(meta_map))

    print("\n" + "=" * 65)
    print(f"Weekly model check — {datetime.now(timezone.utc).date()}")
    print("=" * 65)

    all_pass = True
    for name, meta in meta_map.items():
        artifact_path = _find_latest(models_dir, name)
        if artifact_path is None:
            print(f"  {name:<18}: NO MODEL — run make train first")
            all_pass = False
            continue

        artifact = load_model_artifact(artifact_path)
        if artifact.booster is None:
            print(f"  {name:<18}: BOOSTER MISSING at {artifact_path}")
            all_pass = False
            continue

        df = recent[name]
        if df.empty:
            print(f"  {name:<18}: NO RECENT DATA (run make fetch-data first)")
            all_pass = False
            continue

        horizon = "scalp" if meta["mode"] == "scalp" else "swing"
        entry_thr = meta.get("entry_threshold", _ENTRY_THRESHOLD)
        metrics, prob_diag = _evaluate(
            artifact, df, meta["feature_cols"],
            entry_threshold=entry_thr,
            high_conf_threshold=meta.get("high_conf_threshold", _HIGH_CONF_THRESHOLD),
        )
        passes  = metrics.passes_floor(horizon)
        status  = "PASS" if passes else "FAIL"

        print(
            f"  {name:<18}: AUC={metrics.auc:.3f}  "
            f"PF={metrics.profit_factor:.2f}  "
            f"composite={metrics.composite_score:.3f}  "
            f"n_trades={metrics.n_trades}  [{status}]"
        )
        print(
            f"    model: {artifact_path.name}  |  "
            f"max_prob={prob_diag['max_prob']:.3f}  "
            f"p90_prob={prob_diag['p90_prob']:.3f}  "
            f"label_rate={prob_diag['label_rate']:.3f}  "
            f"threshold={entry_thr}"
        )

        if not passes:
            failures = metrics.failures(horizon)
            print(f"    ! {', '.join(failures)}")
            all_pass = False

    print()
    if all_pass:
        print("All models healthy — no action required.")
    else:
        print("One or more models failed — consider retraining: make train")
    print()

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
