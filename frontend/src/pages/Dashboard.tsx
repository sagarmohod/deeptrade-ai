import { useQuery } from '@tanstack/react-query';
import { ArrowUpRight, ArrowDownRight, Activity, TrendingUp, TrendingDown } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid } from 'recharts';
import { endpoints } from '@/api/client';
import { formatINR, formatNumber, formatPct, formatTime } from '@/lib/utils';
import { cn } from '@/lib/utils';

export function Dashboard() {
  const { data: positions } = useQuery({
    queryKey: ['positions', 'open'],
    queryFn: () => endpoints.positions.list('all', true),
    refetchInterval: 5_000,
  });

  const { data: topSignals } = useQuery({
    queryKey: ['top-signals'],
    queryFn: () => endpoints.signals.top(20),
    refetchInterval: 10_000,
  });

  const { data: pnl } = useQuery({
    queryKey: ['pnl', 'today'],
    queryFn: () => endpoints.pnl.summary('today', 'compare'),
    refetchInterval: 10_000,
  });

  const { data: equity } = useQuery({
    queryKey: ['equity-curve'],
    queryFn: () => endpoints.pnl.equityCurve(1, 'both'),
    refetchInterval: 30_000,
  });

  const livePnL = pnl?.breakdown?.live?.net_pnl ?? 0;
  const paperPnL = pnl?.breakdown?.paper?.net_pnl ?? 0;
  const liveTrades = pnl?.breakdown?.live?.n_trades ?? 0;
  const paperTrades = pnl?.breakdown?.paper?.n_trades ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <span className="text-xs text-fg-subtle">Updated every 5s</span>
      </div>

      {/* Top stats */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard
          label="Today P&L (Live)"
          value={formatINR(livePnL)}
          delta={livePnL >= 0 ? '+' : ''}
          positive={livePnL >= 0}
          subtitle={`${liveTrades} trades`}
        />
        <StatCard
          label="Today P&L (Paper)"
          value={formatINR(paperPnL)}
          delta={paperPnL >= 0 ? '+' : ''}
          positive={paperPnL >= 0}
          subtitle={`${paperTrades} trades`}
        />
        <StatCard
          label="Open Positions"
          value={String(positions?.positions?.length ?? 0)}
          subtitle={`${positions?.positions?.filter(p => p.mode === 'live').length ?? 0} live · ${positions?.positions?.filter(p => p.mode === 'paper').length ?? 0} paper`}
        />
        <StatCard
          label="Active Signals (4h)"
          value={String(topSignals?.signals?.length ?? 0)}
          subtitle="Across all strategies"
        />
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Equity curve */}
        <div className="col-span-2 card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-medium">Equity Curve — Today</h2>
            <div className="flex gap-3 text-xs">
              <LegendItem color="fg" label="Live" />
              <LegendItem color="fg-muted" label="Paper" />
            </div>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--border-default))" />
                <XAxis
                  dataKey="ts"
                  tickFormatter={formatTime}
                  stroke="rgb(var(--fg-subtle))"
                  fontSize={11}
                />
                <YAxis stroke="rgb(var(--fg-subtle))" fontSize={11} tickFormatter={(v) => `₹${v}`} />
                <Tooltip
                  contentStyle={{
                    background: 'rgb(var(--bg-default))',
                    border: '1px solid rgb(var(--border-default))',
                    fontSize: 12,
                  }}
                  formatter={(v: number) => formatINR(v)}
                  labelFormatter={(v) => formatTime(v as string)}
                />
                <Line
                  data={equity?.curves?.live ?? []}
                  type="monotone"
                  dataKey="pnl"
                  stroke="rgb(var(--fg-default))"
                  strokeWidth={2}
                  dot={false}
                  name="Live"
                />
                <Line
                  data={equity?.curves?.paper ?? []}
                  type="monotone"
                  dataKey="pnl"
                  stroke="rgb(var(--fg-muted))"
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  dot={false}
                  name="Paper"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Top signals */}
        <div className="card">
          <h2 className="font-medium mb-4">Top Signals</h2>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {(topSignals?.signals ?? []).slice(0, 10).map((s, i) => (
              <div
                key={i}
                className="flex items-center justify-between py-2 border-b border-border-subtle last:border-0"
              >
                <div className="flex items-center gap-2">
                  {s.direction === 1 ? (
                    <TrendingUp className="w-3.5 h-3.5" />
                  ) : (
                    <TrendingDown className="w-3.5 h-3.5" />
                  )}
                  <div>
                    <div className="text-sm font-medium">{s.symbol}</div>
                    <div className="text-2xs text-fg-subtle uppercase">{s.horizon}</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="num text-sm">{(s.confidence * 100).toFixed(0)}%</div>
                  <div className="text-2xs text-fg-subtle">{formatTime(s.ts)}</div>
                </div>
              </div>
            ))}
            {(!topSignals?.signals || topSignals.signals.length === 0) && (
              <div className="text-sm text-fg-subtle text-center py-8">
                No signals yet today
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Open positions */}
      <div className="card">
        <h2 className="font-medium mb-4">Open Positions</h2>
        {positions?.positions?.length ? (
          <table className="table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Mode</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Avg Entry</th>
                <th>Unrealized P&L</th>
                <th>Strategy</th>
              </tr>
            </thead>
            <tbody>
              {positions.positions.map((p) => (
                <tr key={p.id}>
                  <td className="font-medium">{p.symbol}</td>
                  <td>
                    <span className={cn('badge', p.mode === 'live' ? 'badge-strong' : 'badge-outline')}>
                      {p.mode}
                    </span>
                  </td>
                  <td>{p.side}</td>
                  <td className="num">{p.qty}</td>
                  <td className="num">{formatNumber(p.avg_entry)}</td>
                  <td className={cn('num', p.unrealized_pnl >= 0 ? 'text-fg' : 'text-fg-muted')}>
                    {formatINR(p.unrealized_pnl)}
                  </td>
                  <td className="text-fg-muted text-xs">{p.strategy ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-sm text-fg-subtle text-center py-8">No open positions</div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label, value, delta, positive, subtitle,
}: { label: string; value: string; delta?: string; positive?: boolean; subtitle?: string }) {
  return (
    <div className="card">
      <div className="label mb-2">{label}</div>
      <div className="flex items-baseline gap-2">
        <div className="text-2xl font-semibold tracking-tight num">{value}</div>
        {delta && positive !== undefined && (
          <div className={cn('text-sm', positive ? 'text-fg' : 'text-fg-muted')}>
            {positive ? <ArrowUpRight className="w-3.5 h-3.5 inline" /> : <ArrowDownRight className="w-3.5 h-3.5 inline" />}
          </div>
        )}
      </div>
      {subtitle && <div className="text-xs text-fg-subtle mt-1">{subtitle}</div>}
    </div>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5 text-fg-subtle">
      <div className={`w-3 h-0.5 bg-${color}`} />
      <span>{label}</span>
    </div>
  );
}
