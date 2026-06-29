import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { endpoints } from '@/api/client';
import { cn, formatTime } from '@/lib/utils';

export function Signals() {
  const [horizon, setHorizon] = useState<string>('all');

  const { data, isLoading } = useQuery({
    queryKey: ['signals', horizon],
    queryFn: () => endpoints.signals.list({
      horizon: horizon === 'all' ? undefined : horizon,
      limit: 200,
    }),
    refetchInterval: 5_000,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Signals</h1>
        <div className="flex gap-1 border border-border rounded-md overflow-hidden">
          {['all', 'scalp', 'intraday', 'swing', 'weekly', 'monthly'].map((h) => (
            <button
              key={h}
              onClick={() => setHorizon(h)}
              className={cn(
                'px-3 py-1.5 text-xs uppercase tracking-wide transition-colors',
                horizon === h ? 'bg-fg text-bg' : 'text-fg-muted hover:text-fg'
              )}
            >
              {h}
            </button>
          ))}
        </div>
      </div>

      <div className="card p-0 overflow-hidden">
        {isLoading ? (
          <div className="text-sm text-fg-subtle text-center py-12">Loading…</div>
        ) : (
          <table className="table">
            <thead>
              <tr className="px-4">
                <th className="px-4">Time</th>
                <th>Symbol</th>
                <th>Direction</th>
                <th>Confidence</th>
                <th>Horizon</th>
                <th>Strategy</th>
                <th>Reasoning</th>
              </tr>
            </thead>
            <tbody>
              {data?.signals?.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 num text-fg-muted text-xs">{formatTime(s.ts)}</td>
                  <td className="font-medium">{s.symbol}</td>
                  <td>
                    {s.direction === 1 ? (
                      <span className="inline-flex items-center gap-1 text-fg">
                        <TrendingUp className="w-3.5 h-3.5" /> LONG
                      </span>
                    ) : s.direction === -1 ? (
                      <span className="inline-flex items-center gap-1 text-fg-muted">
                        <TrendingDown className="w-3.5 h-3.5" /> SHORT
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-fg-subtle">
                        <Minus className="w-3.5 h-3.5" /> FLAT
                      </span>
                    )}
                  </td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 bg-bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-fg"
                          style={{ width: `${s.confidence * 100}%` }}
                        />
                      </div>
                      <span className="num text-xs">{(s.confidence * 100).toFixed(0)}%</span>
                    </div>
                  </td>
                  <td>
                    <span className="badge-outline uppercase text-2xs">{s.horizon}</span>
                  </td>
                  <td className="text-fg-muted text-xs font-mono">{s.strategy ?? '—'}</td>
                  <td className="text-fg-muted text-xs max-w-md truncate">{s.reasoning}</td>
                </tr>
              ))}
              {(!data?.signals?.length) && (
                <tr><td colSpan={7} className="text-center text-fg-subtle py-12">No signals yet</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
