"""Quality metrics for model evaluation — v7 §O.

Beyond raw accuracy: AUC, profit factor, Sortino, calibration.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class QualityMetrics:
    """All metrics computed on a backtest result."""

    auc: float = 0.0
    precision_at_65: float = 0.0
    hit_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    sharpe_annualized: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    max_drawdown: float = 0.0
    drawdown_recovery_days: int = 0
    brier_score: float = 0.0
    log_loss: float = 0.0
    composite_score: float = 0.0

    n_trades: int = 0
    n_wins: int = 0
    n_losses: int = 0

    def passes_floor(self, horizon: str = "scalp") -> bool:
        """v7 §O.4 horizon-specific floor thresholds."""
        floors = {
            "scalp": {"auc": 0.54, "pf": 1.20, "sortino": 1.0, "composite": 0.50},
            "intraday": {"auc": 0.55, "pf": 1.30, "sortino": 1.2, "composite": 0.55},
            "swing": {"auc": 0.56, "pf": 1.35, "sortino": 1.3, "composite": 0.60},
            "weekly": {"auc": 0.57, "pf": 1.40, "sortino": 1.4, "composite": 0.65},
            "monthly": {"auc": 0.58, "pf": 1.50, "sortino": 1.5, "composite": 0.70},
        }
        f = floors.get(horizon, floors["intraday"])
        return (
            self.auc >= f["auc"]
            and self.profit_factor >= f["pf"]
            and self.sortino >= f["sortino"]
            and self.composite_score >= f["composite"]
        )

    def failures(self, horizon: str = "scalp") -> list[str]:
        floors = {
            "scalp": {"auc": 0.54, "pf": 1.20, "sortino": 1.0, "composite": 0.50},
            "intraday": {"auc": 0.55, "pf": 1.30, "sortino": 1.2, "composite": 0.55},
            "swing": {"auc": 0.56, "pf": 1.35, "sortino": 1.3, "composite": 0.60},
            "weekly": {"auc": 0.57, "pf": 1.40, "sortino": 1.4, "composite": 0.65},
            "monthly": {"auc": 0.58, "pf": 1.50, "sortino": 1.5, "composite": 0.70},
        }
        f = floors.get(horizon, floors["intraday"])
        out = []
        if self.auc < f["auc"]:
            out.append(f"auc {self.auc:.3f} < {f['auc']}")
        if self.profit_factor < f["pf"]:
            out.append(f"profit_factor {self.profit_factor:.2f} < {f['pf']}")
        if self.sortino < f["sortino"]:
            out.append(f"sortino {self.sortino:.2f} < {f['sortino']}")
        if self.composite_score < f["composite"]:
            out.append(f"composite {self.composite_score:.2f} < {f['composite']}")
        return out


def sigmoid_norm(value: float, midpoint: float = 0.5, slope: float = 10) -> float:
    """Sigmoid normalization — maps value to [0, 1] with midpoint at 0.5 output."""
    return 1.0 / (1.0 + math.exp(-slope * (value - midpoint)))


def compute_composite_score(metrics: QualityMetrics, roundtrip_cost_pct: float = 0.2) -> float:
    """v7 §O.3 weighted composite."""
    weights = {
        "auc": 0.15,
        "precision_at_65": 0.15,
        "profit_factor": 0.25,
        "sortino": 0.15,
        "calmar": 0.10,
        "expectancy_norm": 0.15,
        "brier_inverted": 0.05,
    }

    expectancy_norm = (
        metrics.expectancy / roundtrip_cost_pct if roundtrip_cost_pct > 0 else 0
    )

    components = {
        "auc": sigmoid_norm(metrics.auc, midpoint=0.55, slope=20),
        "precision_at_65": sigmoid_norm(metrics.precision_at_65, midpoint=0.58, slope=20),
        "profit_factor": sigmoid_norm(metrics.profit_factor, midpoint=1.3, slope=2),
        "sortino": sigmoid_norm(metrics.sortino, midpoint=1.5, slope=1),
        "calmar": sigmoid_norm(metrics.calmar, midpoint=0.5, slope=2),
        "expectancy_norm": sigmoid_norm(expectancy_norm, midpoint=1.5, slope=1),
        "brier_inverted": sigmoid_norm(1 - metrics.brier_score, midpoint=0.75, slope=10),
    }

    return sum(weights[k] * components[k] for k in weights)


def deflated_sharpe_ratio(
    observed_sr: float,
    n_trials: int,
    n_observations: int,
    skew_returns: float = 0.0,
    kurt_returns: float = 3.0,
) -> float:
    """Lopez de Prado's deflated Sharpe ratio.

    Returns probability that observed Sharpe is real edge (not multi-test luck).
    """
    if n_trials <= 1 or n_observations <= 1:
        return 0.5

    euler_mascheroni = 0.5772156649

    expected_max_sr = (
        (1 - euler_mascheroni) * _z_score(1 - 1.0 / n_trials)
        + euler_mascheroni * _z_score(1 - 1.0 / (n_trials * math.e))
    )

    sr_var = max(
        0.001,
        (1 - skew_returns * observed_sr + (kurt_returns - 1) / 4 * observed_sr**2)
        / (n_observations - 1),
    )
    sr_std = math.sqrt(sr_var)
    z = (observed_sr - expected_max_sr) / sr_std

    return _normal_cdf(z)


def _z_score(p: float) -> float:
    """Approximate inverse normal CDF (z-score for given probability)."""
    if p <= 0:
        return -10
    if p >= 1:
        return 10
    # Beasley-Springer approximation
    a = [-39.6968302866538, 220.946098424521, -275.928510446969,
         138.357751867269, -30.6647980661472, 2.50662827745924]
    b = [-54.4760987982241, 161.585836858041, -155.698979859887,
         66.8013118877197, -13.2806815528857]
    c = [-0.00778489400243029, -0.322396458041136, -2.40075827716184,
         -2.54973253934373, 4.37466414146497, 2.93816398269878]
    d = [0.00778469570904146, 0.32246712907004, 2.445134137143,
         3.75440866190742]
    p_low = 0.02425
    p_high = 1 - p_low
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p_low <= p <= p_high:
        q = p - 0.5
        r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def _normal_cdf(z: float) -> float:
    """Standard normal CDF using error function."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def compute_metrics_from_trades(trade_returns: list[float]) -> QualityMetrics:
    """Compute QualityMetrics from a list of per-trade returns (as decimals)."""
    if not trade_returns:
        return QualityMetrics()

    arr = np.array(trade_returns)
    wins = arr[arr > 0]
    losses = arr[arr < 0]

    n_trades = len(arr)
    n_wins = len(wins)
    n_losses = len(losses)

    hit_rate = n_wins / n_trades if n_trades > 0 else 0
    avg_win = float(wins.mean()) if len(wins) > 0 else 0
    avg_loss = float(losses.mean()) if len(losses) > 0 else 0

    gross_profit = float(wins.sum())
    gross_loss = abs(float(losses.sum()))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    expectancy = (hit_rate * avg_win) + ((1 - hit_rate) * avg_loss)

    # Sharpe (annualized assuming daily returns)
    if arr.std() > 0:
        sharpe = float((arr.mean() / arr.std()) * math.sqrt(252))
    else:
        sharpe = 0

    # Sortino (downside deviation)
    downside = arr[arr < 0]
    if len(downside) > 0 and downside.std() > 0:
        sortino = float((arr.mean() / downside.std()) * math.sqrt(252))
    else:
        sortino = 0

    # Drawdown
    cumulative = np.cumsum(arr)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    max_dd = float(drawdown.max()) if len(drawdown) > 0 else 0

    calmar = (arr.mean() * 252 / max_dd) if max_dd > 0 else 0

    metrics = QualityMetrics(
        auc=0.55,  # placeholder; computed separately from probabilistic predictions
        precision_at_65=hit_rate,
        hit_rate=hit_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        sharpe_annualized=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown=max_dd,
        n_trades=n_trades,
        n_wins=n_wins,
        n_losses=n_losses,
    )
    metrics.composite_score = compute_composite_score(metrics)
    return metrics
