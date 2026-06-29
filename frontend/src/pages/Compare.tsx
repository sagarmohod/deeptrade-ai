import { useQuery } from '@tanstack/react-query';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { endpoints } from '@/api/client';
import { formatINR, formatTime } from '@/lib/utils';

export function Compare() {
  const { data: pnl } = useQuery({
    queryKey: ['pnl', 'compare', 'month'],
    queryFn: () => endpoints.pnl.summary('month', 'compare'),
  });

  const { data: equity } = useQuery({
    queryKey: ['equity-curve', 30],
    queryFn: () => endpoints.pnl.equityCurve(30, 'both'),
  });

  const paper = pnl?.breakdown?.paper;
  const live = pnl?.breakdown?.live;
  const divergence = paper && live ? Math.abs(paper.net_pnl - live.net_pnl) : 0;
  const correlation = paper?.n_trades && live?.n_trades
    ? Math.min(paper.n_trades, live.n_trades) / Math.max(paper.n_trades, live.n_trades)
    : 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Paper vs Live Comparison</h1>

      <div className="grid grid-cols-3 gap-4">
        <div className="card">
          <div className="label mb-1">P&L Divergence</div>
          <div className="num text-2xl font-semibold">{formatINR(divergence)}</div>
          <div className="text-xs text-fg-subtle mt-1">Absolute difference (month)</div>
        </div>
        <div className="card">
          <div className="label mb-1">Trade Count Match</div>
          <div className="num text-2xl font-semibold">{(correlation * 100).toFixed(0)}%</div>
          <div className="text-xs text-fg-subtle mt-1">{paper?.n_trades ?? 0} paper · {live?.n_trades ?? 0} live</div>
        </div>
        <div className="card">
          <div className="label mb-1">Hit Rate Diff</div>
          <div className="num text-2xl font-semibold">
            {paper && live ? `${((paper.hit_rate - live.hit_rate) * 100).toFixed(1)}%` : '—'}
          </div>
          <div className="text-xs text-fg-subtle mt-1">paper - live</div>
        </div>
      </div>

      <div className="card">
        <h2 className="font-medium mb-4">Equity Curves — Last 30 Days</h2>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--border-default))" />
              <XAxis dataKey="ts" tickFormatter={formatTime} stroke="rgb(var(--fg-subtle))" fontSize={11} />
              <YAxis stroke="rgb(var(--fg-subtle))" fontSize={11} tickFormatter={(v) => `₹${v}`} />
              <Tooltip
                contentStyle={{
                  background: 'rgb(var(--bg-default))',
                  border: '1px solid rgb(var(--border-default))',
                  fontSize: 12,
                }}
                formatter={(v: number) => formatINR(v)}
              />
              <Legend />
              <Line
                data={equity?.curves?.live ?? []}
                type="monotone" dataKey="pnl"
                stroke="rgb(var(--fg-default))" strokeWidth={2}
                dot={false} name="Live"
              />
              <Line
                data={equity?.curves?.paper ?? []}
                type="monotone" dataKey="pnl"
                stroke="rgb(var(--fg-muted))" strokeWidth={1.5}
                strokeDasharray="4 4" dot={false} name="Paper"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
