import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { endpoints } from '@/api/client';
import { cn, formatINR } from '@/lib/utils';

const PERIODS = ['today', 'week', 'month', 'year'] as const;
const MODES = ['paper', 'live', 'compare'] as const;

export function PnL() {
  const [period, setPeriod] = useState<typeof PERIODS[number]>('today');
  const [mode, setMode] = useState<typeof MODES[number]>('compare');

  const { data, isLoading } = useQuery({
    queryKey: ['pnl', period, mode],
    queryFn: () => endpoints.pnl.summary(period, mode),
    refetchInterval: 10_000,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">P&L</h1>
        <div className="flex gap-3">
          <div className="flex border border-border rounded-md overflow-hidden">
            {PERIODS.map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={cn(
                  'px-3 py-1.5 text-xs uppercase tracking-wide transition-colors',
                  period === p ? 'bg-fg text-bg' : 'text-fg-muted hover:text-fg'
                )}
              >
                {p}
              </button>
            ))}
          </div>
          <div className="flex border border-border rounded-md overflow-hidden">
            {MODES.map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={cn(
                  'px-3 py-1.5 text-xs uppercase tracking-wide transition-colors',
                  mode === m ? 'bg-fg text-bg' : 'text-fg-muted hover:text-fg'
                )}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="text-sm text-fg-subtle">Loading...</div>
      ) : (
        <div className="grid grid-cols-2 gap-6">
          {Object.entries(data?.breakdown ?? {}).map(([modeKey, b]) => (
            <div key={modeKey} className="card space-y-4">
              <div className="flex items-baseline justify-between">
                <h2 className="font-medium uppercase tracking-wide text-sm">{modeKey}</h2>
                <span className="text-xs text-fg-subtle">{b.n_trades} trades</span>
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2">
                <div>
                  <div className="label mb-1">Net P&L</div>
                  <div className={cn(
                    'num text-2xl font-semibold',
                    b.net_pnl >= 0 ? 'text-fg' : 'text-fg-muted'
                  )}>
                    {formatINR(b.net_pnl)}
                  </div>
                </div>
                <div>
                  <div className="label mb-1">Hit Rate</div>
                  <div className="num text-2xl font-semibold">
                    {(b.hit_rate * 100).toFixed(0)}%
                  </div>
                </div>
                <div>
                  <div className="label mb-1">Gross P&L</div>
                  <div className="num">{formatINR(b.gross_pnl)}</div>
                </div>
                <div>
                  <div className="label mb-1">Total Fees</div>
                  <div className="num text-fg-muted">{formatINR(b.fees_total)}</div>
                </div>
                <div>
                  <div className="label mb-1">Wins</div>
                  <div className="num">{b.n_wins}</div>
                </div>
                <div>
                  <div className="label mb-1">Losses</div>
                  <div className="num">{b.n_losses}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
