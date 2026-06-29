export function Backtests() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Backtests</h1>
      <div className="card text-sm text-fg-muted">
        Backtest UI coming soon. For now, run via CLI:
        <pre className="mt-3 font-mono text-xs bg-bg-muted p-3 rounded">
{`python scripts/run_backtest.py \\
  --strategy orb_nifty_scalp \\
  --start 2023-01-01 \\
  --end 2024-12-31`}
        </pre>
      </div>
    </div>
  );
}
