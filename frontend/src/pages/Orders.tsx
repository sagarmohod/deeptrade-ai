import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ClipboardList } from 'lucide-react';
import { endpoints, type Order } from '@/api/client';
import { cn } from '@/lib/utils';

type Tab = 'today' | 'history';
type ModeFilter = 'paper' | 'live' | 'all';

export function Orders() {
  const [tab, setTab] = useState<Tab>('today');
  const [mode, setMode] = useState<ModeFilter>('paper');

  const todayQ = useQuery({
    queryKey: ['orders-today', mode],
    queryFn: () => endpoints.orders.today(mode),
    refetchInterval: 10_000,
    enabled: tab === 'today',
  });

  const historyQ = useQuery({
    queryKey: ['orders-history', mode],
    queryFn: () => endpoints.orders.history(mode, 30),
    refetchInterval: 30_000,
    enabled: tab === 'history',
  });

  const active = tab === 'today' ? todayQ : historyQ;
  const orders = active.data?.orders ?? [];

  return (
    <div className="space-y-5">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <ClipboardList className="w-5 h-5" />
          Orders
        </h1>

        {/* Mode filter */}
        <div className="flex border border-border rounded-md overflow-hidden text-xs">
          {(['paper', 'live', 'all'] as ModeFilter[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={cn(
                'px-3 py-1.5 uppercase tracking-wide transition-colors',
                mode === m ? 'bg-fg text-bg font-medium' : 'text-fg-muted hover:text-fg'
              )}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border gap-1">
        {(['today', 'history'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px',
              tab === t
                ? 'border-fg text-fg'
                : 'border-transparent text-fg-muted hover:text-fg'
            )}
          >
            {t === 'today' ? "Today" : "History (30d)"}
          </button>
        ))}
        <span className="ml-auto self-center text-xs text-fg-subtle pr-1">
          {active.data?.count ?? 0} orders
        </span>
      </div>

      {/* Table */}
      {active.isLoading ? (
        <div className="text-sm text-fg-subtle py-8 text-center">Loading…</div>
      ) : orders.length === 0 ? (
        <div className="text-sm text-fg-subtle py-8 text-center">
          No orders found.{' '}
          {mode === 'paper' && tab === 'today' && (
            <span>Paper trades appear here during market hours (9:15–15:30 IST).</span>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <Th>Time (IST)</Th>
                <Th>Symbol</Th>
                <Th>Side</Th>
                <Th>Qty</Th>
                <Th>Fill Price</Th>
                <Th>Status</Th>
                <Th>Strategy</Th>
                <Th>Mode</Th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <OrderRow key={o.id} order={o} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function OrderRow({ order: o }: { order: Order }) {
  const ts = new Date(o.ts_created);
  const timeIST = ts.toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  const dateIST = ts.toLocaleDateString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
  });

  return (
    <tr className="border-b border-border/50 hover:bg-bg-muted/40 transition-colors">
      <td className="py-2.5 pr-4">
        <div className="num text-xs">{timeIST}</div>
        <div className="text-2xs text-fg-subtle">{dateIST}</div>
      </td>
      <td className="py-2.5 pr-4 font-medium">{o.symbol}</td>
      <td className="py-2.5 pr-4">
        <span
          className={cn(
            'inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase',
            o.side === 'BUY'
              ? 'bg-green-500/10 text-green-600 dark:text-green-400'
              : 'bg-red-500/10 text-red-600 dark:text-red-400'
          )}
        >
          {o.side}
        </span>
      </td>
      <td className="py-2.5 pr-4 num">{o.qty}</td>
      <td className="py-2.5 pr-4 num">
        {o.avg_fill_price != null
          ? `₹${o.avg_fill_price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
          : o.limit_price != null
          ? `₹${o.limit_price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
          : '—'}
      </td>
      <td className="py-2.5 pr-4">
        <StatusBadge status={o.status} />
      </td>
      <td className="py-2.5 pr-4 text-fg-muted text-xs">{o.strategy ?? '—'}</td>
      <td className="py-2.5">
        <span
          className={cn(
            'inline-block px-1.5 py-0.5 rounded text-2xs uppercase tracking-wide',
            o.mode === 'paper' ? 'bg-bg-muted text-fg-subtle' : 'bg-orange-500/10 text-orange-600 dark:text-orange-400'
          )}
        >
          {o.mode}
        </span>
      </td>
    </tr>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === 'FILLED' ? 'text-green-600 dark:text-green-400 bg-green-500/10' :
    status === 'REJECTED' || status === 'CANCELLED' ? 'text-red-600 dark:text-red-400 bg-red-500/10' :
    status === 'PENDING' ? 'text-yellow-600 dark:text-yellow-400 bg-yellow-500/10' :
    'text-fg-muted bg-bg-muted';

  return (
    <span className={cn('inline-block px-2 py-0.5 rounded text-xs font-medium', color)}>
      {status}
    </span>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="py-2.5 pr-4 text-xs font-medium text-fg-subtle uppercase tracking-wide">
      {children}
    </th>
  );
}
