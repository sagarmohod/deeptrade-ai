import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle, CheckCircle2, XCircle, Zap } from 'lucide-react';
import { endpoints, type AutoScalpingEnableRequest } from '@/api/client';
import { cn, formatINR } from '@/lib/utils';

export function AutoScalping() {
  const qc = useQueryClient();
  const [confirmText, setConfirmText] = useState('');

  const { data: status, isLoading } = useQuery({
    queryKey: ['auto-scalping-status'],
    queryFn: endpoints.trading.autoScalpingStatus,
    refetchInterval: 5_000,
  });

  const { register, handleSubmit } = useForm<AutoScalpingEnableRequest>({
    defaultValues: {
      max_total_live_trades: 20,
      max_live_trades_per_day: 10,
      max_concurrent_positions: 1,
      max_capital_at_risk_total: 15000,
      max_capital_per_trade: 5000,
      broker_balance_min_buffer: 500,
      enabled_strategies: [],
      confirmation_phrase: '',
    },
  });

  const enable = useMutation({
    mutationFn: (req: AutoScalpingEnableRequest) => endpoints.trading.enableAutoScalping(req),
    onSuccess: () => {
      toast.success('Live auto-scalping enabled');
      qc.invalidateQueries({ queryKey: ['auto-scalping-status'] });
    },
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  const disable = useMutation({
    mutationFn: () => endpoints.trading.disableAutoScalping(),
    onSuccess: () => {
      toast.success('Live auto-scalping disabled');
      qc.invalidateQueries({ queryKey: ['auto-scalping-status'] });
    },
  });

  const paper = status?.paper;
  const live = status?.live;

  return (
    <div className="space-y-6 max-w-4xl">
      <h1 className="text-2xl font-semibold tracking-tight">Auto Scalping</h1>

      {/* ── Paper Trading (always on) ───────────────────────────────── */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-medium flex items-center gap-2">
            <Zap className="w-4 h-4" />
            Paper Trading
          </h2>
          <span className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-green-500/10 text-green-600 dark:text-green-400">
            <CheckCircle2 className="w-3.5 h-3.5" />
            ALWAYS ACTIVE
          </span>
        </div>

        {isLoading ? (
          <div className="text-sm text-fg-subtle">Loading…</div>
        ) : paper?.enabled ? (
          <div className="grid grid-cols-3 gap-6 text-sm">
            <Metric label="Engine" value="RUNNING" highlight />
            <Metric label="Trades Today" value={String(paper.trades_executed_today ?? 0)} />
            <Metric
              label="Simulated Capital"
              value={formatINR(paper.max_capital_at_risk_total ?? 0)}
            />
          </div>
        ) : (
          <p className="text-sm text-fg-muted">
            Start with <code className="font-mono bg-bg-muted px-1 rounded">make paper</code> to activate the paper engine.
          </p>
        )}
      </div>

      {/* ── Live Trading (Zerodha) ──────────────────────────────────── */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-medium flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            Live Trading — Zerodha
          </h2>
          {live?.enabled ? (
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-orange-500/10 text-orange-600 dark:text-orange-400">
                <CheckCircle2 className="w-3.5 h-3.5" />
                LIVE ENABLED
              </span>
              <button
                onClick={() => disable.mutate()}
                className="btn-secondary text-xs uppercase tracking-wide"
              >
                Disable
              </button>
            </div>
          ) : (
            <span className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-bg-muted text-fg-muted">
              <XCircle className="w-3.5 h-3.5" />
              DISABLED
            </span>
          )}
        </div>

        {live?.enabled ? (
          <div className="grid grid-cols-4 gap-4 text-sm">
            <Metric label="Trades Today" value={`${live.trades_executed_today ?? 0}/${live.max_live_trades_per_day ?? '—'}`} />
            <Metric label="Trades Total" value={`${live.trades_executed_total ?? 0}/${live.max_total_live_trades ?? '—'}`} />
            <Metric
              label="Capital at Risk"
              value={formatINR(live.capital_currently_at_risk ?? 0)}
              subtitle={`Cap: ${formatINR(live.max_capital_at_risk_total ?? 0)}`}
            />
            <Metric label="Strategies" value={(live.enabled_strategies ?? []).join(', ') || '—'} />
          </div>
        ) : (
          <p className="text-sm text-fg-muted mb-0">
            Real money trading via Zerodha. Configure limits below then type <code className="font-mono bg-bg-muted px-1 rounded">ENABLE_LIVE</code> to activate.
          </p>
        )}
      </div>

      {/* ── Enable form (only shown when live is off) ───────────────── */}
      {!live?.enabled && (
        <form
          onSubmit={handleSubmit((data) => enable.mutate({ ...data, confirmation_phrase: confirmText }))}
          className="space-y-4"
        >
          <div className="card space-y-4">
            <h3 className="font-medium">Trade Limits</h3>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Max Total Trades">
                <input {...register('max_total_live_trades', { valueAsNumber: true, required: true })}
                  type="number" min={1} className="input num" />
              </Field>
              <Field label="Max Per Day">
                <input {...register('max_live_trades_per_day', { valueAsNumber: true, required: true })}
                  type="number" min={1} className="input num" />
              </Field>
              <Field label="Max Concurrent Positions">
                <input {...register('max_concurrent_positions', { valueAsNumber: true, required: true })}
                  type="number" min={1} className="input num" />
              </Field>
              <Field label="Per-Trade Capital Cap (₹)">
                <input {...register('max_capital_per_trade', { valueAsNumber: true, required: true })}
                  type="number" min={1} className="input num" />
              </Field>
              <Field label="Total Capital at Risk (₹)">
                <input {...register('max_capital_at_risk_total', { valueAsNumber: true, required: true })}
                  type="number" min={1} className="input num" />
              </Field>
              <Field label="Broker Balance Buffer (₹)">
                <input {...register('broker_balance_min_buffer', { valueAsNumber: true })}
                  type="number" min={0} className="input num" />
              </Field>
            </div>
          </div>

          <div className="card">
            <h3 className="font-medium mb-3">Enabled Strategies</h3>
            <div className="space-y-2 text-sm">
              {[
                { id: 'scalp_1m', label: 'Scalp 1m — NIFTY/BANKNIFTY indices' },
                { id: 'scalp_15m', label: 'Scalp 15m — NIFTY/BANKNIFTY indices' },
                { id: 'momentum_15m', label: 'Momentum 15m — extended hold' },
              ].map((s) => (
                <label key={s.id} className="flex items-center gap-3 cursor-pointer">
                  <input type="checkbox" value={s.id} {...register('enabled_strategies')}
                    className="w-4 h-4 accent-fg" />
                  <span>{s.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="card border-2 border-border-strong">
            <div className="flex items-start gap-3 mb-4">
              <AlertTriangle className="w-5 h-5 mt-0.5" />
              <div className="space-y-1">
                <h3 className="font-medium">Confirm Live Trading</h3>
                <p className="text-sm text-fg-muted">
                  This enables real-money orders via Zerodha MIS. Type{' '}
                  <code className="font-mono bg-bg-muted px-1 rounded">ENABLE_LIVE</code> to confirm.
                </p>
              </div>
            </div>
            <input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              className="input font-mono"
              placeholder="ENABLE_LIVE"
            />
          </div>

          <button
            type="submit"
            disabled={confirmText !== 'ENABLE_LIVE' || enable.isPending}
            className="btn-primary w-full h-12"
          >
            {enable.isPending ? 'Enabling…' : 'Enable Live Auto Scalping'}
          </button>
        </form>
      )}
    </div>
  );
}

function Metric({
  label, value, subtitle, highlight,
}: { label: string; value: string; subtitle?: string; highlight?: boolean }) {
  return (
    <div>
      <div className="label mb-1">{label}</div>
      <div className={cn('num font-medium', highlight ? 'text-base' : 'text-sm')}>{value}</div>
      {subtitle && <div className="text-2xs text-fg-subtle mt-0.5">{subtitle}</div>}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="label mb-2 block">{label}</label>
      {children}
    </div>
  );
}
