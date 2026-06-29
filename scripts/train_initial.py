"""Initial model training — trains LightGBM binary classifiers from historical DB data.

Models:
  scalp_1m    — NIFTY 50 + BANKNIFTY 1-min ORB scalping
  scalp_15m   — NIFTY 50 + BANKNIFTY 15-min ORB scalping
  swing_1d    — Nifty 100 daily Connors RSI swing

Usage:
    python scripts/train_initial.py                    # train all models
    python scripts/train_initial.py --model scalp_1m   # one model only
    python scripts/train_initial.py --dry-run          # dataset stats, no training

Time estimates on M3 Pro 18GB:
    scalp_1m:  ~30 min  (dense dataset)
    scalp_15m: ~10 min
    swing_1d:  ~5 min
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import structlog
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score

from core.ml import (
    ModelArtifact,
    QualityMetrics,
    WalkForwardWindow,
    build_walk_forward_schedule,
    compute_composite_score,
    compute_metrics_from_trades,
    make_version_string,
    progressive_training_stages,
    save_model_artifact,
)
from core.ml.features import (
    SCALP_FEATURE_COLS,
    SWING_FEATURE_COLS,
    build_scalp_dataset_async,
    build_swing_dataset_async,
)

logger = structlog.get_logger(__name__)

_COST_PCT = 0.0006  # 0.06% round-trip — applied to all training metrics

# ── Symbol universes ──────────────────────────────────────────────────────────

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

# ── Model configuration ───────────────────────────────────────────────────────

MODEL_CONFIGS: dict[str, dict[str, Any]] = {
    "scalp_1m": {
        "mode": "scalp",
        "symbols": _INDEX_SYMBOLS,
        "exchange": "NSE",
        "timeframe": "1m",
        "history_start": date(2020, 1, 1),  # 1m data is large — 5 years sufficient
        "feature_cols": SCALP_FEATURE_COLS,
        "entry_threshold": 0.55,
        "high_conf_threshold": 0.65,
    },
    "scalp_15m": {
        "mode": "scalp",
        "symbols": _INDEX_SYMBOLS,
        "exchange": "NSE",
        "timeframe": "15m",
        "history_start": date(2018, 1, 1),
        "feature_cols": SCALP_FEATURE_COLS,
        "entry_threshold": 0.50,  # label_rate ~17% → calibrated probs rarely hit 0.55
        "high_conf_threshold": 0.60,
    },
    "swing_1d": {
        "mode": "swing",
        "symbols": _NIFTY_100,
        "exchange": "NSE",
        "timeframe": "1d",
        # Equity data is fetched from 2 years ago — match that window.
        # progressive_training_stages needs 36+ months which exceeds available data,
        # so use build_walk_forward_schedule with smaller windows instead.
        # hi6m (120-bar warmup) vs hi52w (252-bar) saves ~6 months of effective data.
        "history_start": date.today() - timedelta(days=730),
        "feature_cols": SWING_FEATURE_COLS,
        "wf_train_months": 6,
        "wf_val_months": 2,
        "wf_test_months": 2,
        "entry_threshold": 0.42,   # raised: 0.35 triggers 41% of bars in backtest
        "high_conf_threshold": 0.52,
    },
    # ── Longer-hold strategies targeting bigger moves ─────────────────────────
    # momentum_15m: 90-min hold (6 × 15m bars), 0.5% minimum move.
    # Targets real momentum rather than micro-scalping; fewer but higher-quality signals.
    "momentum_15m": {
        "mode": "scalp",
        "symbols": _INDEX_SYMBOLS,
        "exchange": "NSE",
        "timeframe": "15m",
        "history_start": date(2018, 1, 1),
        "feature_cols": SCALP_FEATURE_COLS,
        "forward_bars": 6,          # 6 × 15m = 90-min hold
        "label_threshold": 0.005,   # 0.5% minimum gross move
        "entry_threshold": 0.52,
        "high_conf_threshold": 0.62,
    },
    # intraday_1h: 3-hour hold (3 × 1h bars), 0.6% minimum move.
    # Half-session trend-following; expects fewer but more decisive signals.
    "intraday_1h": {
        "mode": "scalp",
        "symbols": _INDEX_SYMBOLS,
        "exchange": "NSE",
        "timeframe": "1h",
        "history_start": date(2018, 1, 1),
        "feature_cols": SCALP_FEATURE_COLS,
        "forward_bars": 3,          # 3 × 1h = 3-hour hold
        "label_threshold": 0.006,   # 0.6% minimum gross move
        "entry_threshold": 0.52,
        "high_conf_threshold": 0.62,
    },
}

# ── LightGBM hyperparameters ──────────────────────────────────────────────────

def _lgb_params(label_rate: float, mode: str) -> dict[str, Any]:
    """Build LightGBM params tuned per model type and class imbalance."""
    # scale_pos_weight corrects class imbalance without discarding negatives
    pos_weight = max(1.0, (1.0 - label_rate) / label_rate) if 0 < label_rate < 0.5 else 1.0

    base: dict[str, Any] = {
        "objective":          "binary",
        "metric":             "auc",
        "learning_rate":      0.05,
        "feature_fraction":   0.8,
        "bagging_fraction":   0.8,
        "bagging_freq":       5,
        "lambda_l1":          0.1,
        "lambda_l2":          0.1,
        "verbose":            -1,
        "n_jobs":             -1,
        "scale_pos_weight":   round(pos_weight, 2),
    }
    if mode == "swing":
        base.update({
            "num_leaves":          31,    # simpler model — less data
            "min_child_samples":   80,    # stronger regularization for swing
            "lambda_l1":           0.3,
            "lambda_l2":           0.3,
        })
    else:
        base.update({
            "num_leaves":          63,
            "min_child_samples":   50,
        })
    return base

_MIN_ROWS = 300
_ENTRY_THRESHOLD = 0.55
_HIGH_CONF_THRESHOLD = 0.65


# ── Dataset loading (single event loop) ──────────────────────────────────────

async def _load_all_datasets(
    configs: dict[str, dict[str, Any]]
) -> dict[str, pd.DataFrame]:
    """Load all feature datasets inside one event loop.

    asyncpg binds connections to the event loop they were created on.
    Calling asyncio.run() multiple times would create different loops and
    cause 'Future attached to a different loop'. Loading everything here
    in a single coroutine avoids that.
    """
    datasets: dict[str, pd.DataFrame] = {}
    for name, cfg in configs.items():
        hs = cfg["history_start"]
        he = date.today()
        s = datetime(hs.year, hs.month, hs.day, tzinfo=timezone.utc)
        e = datetime(he.year, he.month, he.day, 23, 59, 59, tzinfo=timezone.utc)

        if cfg["mode"] == "scalp":
            df = await build_scalp_dataset_async(
                cfg["symbols"], cfg["exchange"], cfg["timeframe"], s, e,
                forward_bars=cfg.get("forward_bars"),
                label_threshold=cfg.get("label_threshold"),
            )
        else:
            df = await build_swing_dataset_async(
                cfg["symbols"], cfg["exchange"], s, e,
                forward_bars=cfg.get("forward_bars"),
                label_threshold=cfg.get("label_threshold"),
            )
        datasets[name] = df
    return datasets


# ── Walk-forward helpers ──────────────────────────────────────────────────────

def _split_window(
    df: pd.DataFrame, window: WalkForwardWindow
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    t = df["time"].dt.date
    train = df[(t >= window.train_start) & (t <  window.train_end)]
    val   = df[(t >= window.val_start)   & (t <  window.val_end)]
    test  = df[(t >= window.test_start)  & (t <= window.test_end)]
    return train, val, test


def _simulate_pf(
    df: pd.DataFrame,
    booster: lgb.Booster,
    calibrator: IsotonicRegression,
    feature_cols: list[str],
    entry_threshold: float,
    cost_pct: float = _COST_PCT,
) -> tuple[float, int]:
    """Quick backtest on df. Returns (net_profit_factor, n_trades)."""
    available = [c for c in feature_cols if c in df.columns]
    if not available or "fwd_return" not in df.columns:
        return 0.0, 0
    raw   = booster.predict(df[available].values)
    probs = calibrator.predict(raw)
    mask  = probs > entry_threshold
    n     = int(mask.sum())
    if n < 5:
        return 0.0, n
    net    = df["fwd_return"].values[mask] - cost_pct
    wins   = net[net > 0]
    losses = net[net < 0]
    gp = float(wins.sum())        if len(wins)   > 0 else 0.0
    gl = float(abs(losses.sum())) if len(losses) > 0 else 0.0
    pf = round(gp / gl, 3) if gl > 0 else 0.0
    return pf, n


def _train_one_window(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    feature_cols: list[str],
    entry_threshold: float = _ENTRY_THRESHOLD,
    high_conf_threshold: float = _HIGH_CONF_THRESHOLD,
    mode: str = "scalp",
    cost_pct: float = _COST_PCT,
) -> tuple[lgb.Booster, IsotonicRegression, QualityMetrics, float] | None:
    """Train + calibrate on one window. Returns (booster, calibrator, metrics, test_pf) or None."""
    if len(train) < _MIN_ROWS or len(val) < _MIN_ROWS or len(test) < _MIN_ROWS:
        return None

    X_train = train[feature_cols].values
    y_train = train["label"].values
    X_val   = val[feature_cols].values
    y_val   = val["label"].values
    X_test  = test[feature_cols].values
    y_test  = test["label"].values
    fwd_returns = test["fwd_return"].values if "fwd_return" in test.columns else None

    label_rate = float(y_train.mean()) if len(y_train) > 0 else 0.05
    params = _lgb_params(label_rate, mode)

    train_ds = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols, free_raw_data=True)
    val_ds   = lgb.Dataset(X_val,   label=y_val,   reference=train_ds,        free_raw_data=True)

    callbacks = [
        lgb.early_stopping(stopping_rounds=50, verbose=False),
        lgb.log_evaluation(period=500),
    ]
    booster = lgb.train(
        params,
        train_ds,
        num_boost_round=1000,
        valid_sets=[val_ds],
        callbacks=callbacks,
    )

    # Isotonic calibration on val predictions
    val_probs  = booster.predict(X_val)
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(val_probs, y_val)

    # Evaluate on test set
    raw_probs  = booster.predict(X_test)
    test_probs = calibrator.predict(raw_probs)

    try:
        auc = float(roc_auc_score(y_test, test_probs))
    except ValueError:
        auc = 0.5

    # Quick backtest on test set (net returns after cost)
    test_pf, _ = _simulate_pf(test, booster, calibrator, feature_cols, entry_threshold, cost_pct)

    trade_mask = test_probs > entry_threshold
    if trade_mask.sum() < 10:
        metrics = QualityMetrics(auc=auc)
        metrics.composite_score = compute_composite_score(metrics)
        return booster, calibrator, metrics, test_pf

    if fwd_returns is not None:
        trade_returns = (fwd_returns[trade_mask] - cost_pct).tolist()
    else:
        trade_returns = [(0.002 - cost_pct) if y == 1 else (-0.002 - cost_pct)
                         for y in y_test[trade_mask]]

    metrics = compute_metrics_from_trades(trade_returns)
    metrics.auc = auc

    high_mask = test_probs > high_conf_threshold
    if high_mask.sum() > 10:
        metrics.precision_at_65 = float(y_test[high_mask].mean())

    metrics.brier_score = float(np.mean((test_probs - y_test) ** 2))
    metrics.composite_score = compute_composite_score(metrics)
    return booster, calibrator, metrics, test_pf


# ── Main training pipeline ────────────────────────────────────────────────────

def train_model(
    name: str,
    cfg: dict[str, Any],
    df: pd.DataFrame,
    output_dir: Path,
    n_stages: int,
) -> ModelArtifact | None:
    """Walk-forward train on pre-loaded dataset, pick best stage, save artifact."""
    if df.empty:
        logger.error("empty_dataset", name=name)
        return None

    logger.info("training_started", name=name, mode=cfg["mode"],
                tf=cfg["timeframe"], rows=len(df),
                label_rate=round(float(df["label"].mean()), 3))

    history_start = cfg["history_start"]
    history_end   = date.today()

    try:
        wf_train = cfg.get("wf_train_months", 24)
        wf_val   = cfg.get("wf_val_months",   6)
        wf_test  = cfg.get("wf_test_months",  6)
        if wf_train == 24 and wf_val == 6 and wf_test == 6:
            stages = progressive_training_stages(history_start, history_end, n_stages=n_stages)
        else:
            stages = build_walk_forward_schedule(
                history_start, history_end,
                n_steps=n_stages,
                train_months=wf_train,
                val_months=wf_val,
                test_months=wf_test,
            )
    except ValueError as e:
        logger.error("schedule_failed", name=name, error=str(e))
        return None

    if not stages:
        logger.error("no_stages_built", name=name)
        return None

    feature_cols = cfg["feature_cols"]
    best_booster = best_calibrator = best_metrics = best_window = None
    best_score   = -1.0
    best_test_pf = 0.0

    for i, window in enumerate(stages):
        train, val, test = _split_window(df, window)
        logger.info(
            "stage_start", name=name, stage=i + 1, total=len(stages),
            train_rows=len(train), val_rows=len(val), test_rows=len(test),
        )

        result = _train_one_window(
            train, val, test, feature_cols,
            entry_threshold=cfg.get("entry_threshold", _ENTRY_THRESHOLD),
            high_conf_threshold=cfg.get("high_conf_threshold", _HIGH_CONF_THRESHOLD),
            mode=cfg["mode"],
        )
        if result is None:
            logger.warning("stage_skipped", name=name, stage=i + 1, reason="too_few_rows")
            continue

        booster, calibrator, metrics, test_pf = result
        _, n_signals = _simulate_pf(
            test, booster, calibrator, feature_cols,
            cfg.get("entry_threshold", _ENTRY_THRESHOLD),
        )

        # Weight backtest PF alongside composite: normalise PF to [0,1] around midpoint 1.5
        pf_norm  = min(test_pf / 2.0, 1.0) if test_pf > 0 else 0.0
        score    = 0.45 * metrics.composite_score + 0.55 * pf_norm

        logger.info(
            "stage_done", name=name, stage=i + 1,
            auc=round(metrics.auc, 4),
            pf_val=round(metrics.profit_factor, 3),
            pf_test=round(test_pf, 3),
            sortino=round(metrics.sortino, 3),
            composite=round(metrics.composite_score, 4),
            selection_score=round(score, 4),
            n_trades=metrics.n_trades,
        )
        print(
            f"    stage {i+1:>2}/{len(stages)}  "
            f"window {window.test_start}→{window.test_end}  "
            f"AUC={metrics.auc:.3f}  "
            f"PF_val={metrics.profit_factor:.2f}  "
            f"PF_test={test_pf:.2f}  "
            f"n={n_signals}  "
            f"score={score:.3f}"
            + (" ★" if score > best_score else "")
        )

        if score > best_score:
            best_score      = score
            best_booster    = booster
            best_calibrator = calibrator
            best_metrics    = metrics
            best_window     = window
            best_test_pf    = test_pf

    if best_booster is None:
        logger.error("no_valid_stage", name=name)
        return None

    # Trailing period analysis on the full dataset using the best-stage model
    print(f"\n  {name} — trailing PF (best model, full dataset):")
    entry_thr = cfg.get("entry_threshold", _ENTRY_THRESHOLD)
    for _label, _days in [("1m", 30), ("3m", 90), ("6m", 180), ("12m", 365)]:
        _cutoff   = date.today() - timedelta(days=_days)
        _slice    = df[df["time"].dt.date >= _cutoff]
        _pf, _n   = _simulate_pf(_slice, best_booster, best_calibrator, feature_cols, entry_thr)
        print(f"    {_label:>3}: PF={_pf:.2f}  n_trades={_n}")
    print()

    horizon  = "scalp" if cfg["mode"] == "scalp" else "swing"
    passes   = best_metrics.passes_floor(horizon)
    failures = best_metrics.failures(horizon) if not passes else []

    if passes:
        logger.info("quality_floor_passed", name=name, composite=round(best_score, 4))
    else:
        logger.warning("quality_floor_failed", name=name, failures=failures)

    version  = make_version_string(name)
    artifact = ModelArtifact(
        name=name,
        version=version,
        horizon=horizon,
        target=f"label_{cfg['timeframe']}",
        trained_at=datetime.now(timezone.utc),
        train_window_start=best_window.train_start,
        train_window_end=best_window.train_end,
        artifact_path=output_dir,
        feature_set_version="fs_v1",
        booster=best_booster,
        calibrator=best_calibrator,
        metrics={
            "auc_oos":         round(best_metrics.auc, 4),
            "precision_at_65": round(best_metrics.precision_at_65, 4),
            "profit_factor":   round(best_metrics.profit_factor, 4),
            "sortino":         round(best_metrics.sortino, 4),
            "composite_score": round(best_metrics.composite_score, 4),
            "n_trades_oos":    best_metrics.n_trades,
            "backtest_pf_test": round(best_test_pf, 4),
            "passes_floor":    passes,
            "failures":        failures,
        },
    )

    saved_path = save_model_artifact(artifact, output_dir)
    (saved_path / "features.json").write_text(json.dumps(feature_cols, indent=2))
    logger.info("model_saved", name=name, version=version, path=str(saved_path))
    return artifact


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Train DeepTrade AI LightGBM models")
    parser.add_argument(
        "--model", choices=list(MODEL_CONFIGS) + ["all"], default="all",
        help="Model to train (default: all)",
    )
    parser.add_argument("--output-dir", default="./models")
    parser.add_argument("--n-stages", type=int, default=5, help="Walk-forward stages")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print dataset stats only — no training")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    configs: dict[str, dict[str, Any]] = (
        MODEL_CONFIGS if args.model == "all"
        else {args.model: MODEL_CONFIGS[args.model]}
    )

    # Load all datasets in a single asyncio.run() — avoids asyncpg "different loop" error
    # when multiple asyncio.run() calls try to reuse the same connection pool.
    logger.info("loading_datasets", models=list(configs))
    datasets = asyncio.run(_load_all_datasets(configs))

    if args.dry_run:
        print("Dry-run — dataset summary\n")
        for name, df in datasets.items():
            if df.empty:
                print(f"  {name:<18}: NO DATA")
            else:
                print(
                    f"  {name:<18}: {len(df):>8} rows  "
                    f"label_rate={df['label'].mean():.3f}  "
                    f"symbols={df['symbol'].nunique()}  "
                    f"features={len(configs[name]['feature_cols'])}"
                )
        return

    results: list[tuple[str, ModelArtifact | None]] = []
    for name, cfg in configs.items():
        artifact = train_model(name, cfg, datasets[name], output_dir, args.n_stages)
        results.append((name, artifact))

    print("\n" + "=" * 65)
    print("Training complete")
    print("=" * 65)
    for name, artifact in results:
        if artifact is None:
            print(f"  {name:<18}: FAILED — check logs")
        else:
            m      = artifact.metrics
            status = "PASS" if m.get("passes_floor") else "FAIL"
            print(
                f"  {name:<18}: AUC={m['auc_oos']:.3f}  "
                f"PF={m['profit_factor']:.2f}  "
                f"composite={m['composite_score']:.3f}  [{status}]"
            )
            print(f"    → {artifact.artifact_path}")
            if not m.get("passes_floor") and m.get("failures"):
                print(f"    ! {', '.join(m['failures'])}")
    print()
    print("Next: make deploy-model name=<model> version=<version>")
    print()


if __name__ == "__main__":
    main()
