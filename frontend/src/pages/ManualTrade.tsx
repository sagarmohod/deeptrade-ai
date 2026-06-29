import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Search, AlertCircle } from 'lucide-react';
import { endpoints, type ManualOrderRequest } from '@/api/client';
import { cn, formatINR, formatNumber } from '@/lib/utils';

export function ManualTrade() {
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [mode, setMode] = useState<'paper' | 'live'>('paper');

  const { register, handleSubmit, watch, formState: { errors } } = useForm<ManualOrderRequest>({
    defaultValues: {
      symbol: '',
      qty: 1,
      order_type: 'LIMIT',
      product: 'MIS',
      mode: 'paper',
    },
  });

  const placeOrder = useMutation({
    mutationFn: (req: ManualOrderRequest) => endpoints.trading.placeManualOrder(req),
    onSuccess: () => toast.success('Order placed'),
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  const onSubmit = (data: ManualOrderRequest) => {
    placeOrder.mutate({ ...data, side, mode });
  };

  const qty = watch('qty') || 0;
  const limitPrice = watch('limit_price') || 0;
  const estCost = Number(qty) * Number(limitPrice);

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Manual Trade</h1>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        {/* Symbol search */}
        <div className="card">
          <label className="label mb-2 block">Symbol</label>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-fg-subtle" />
            <input
              {...register('symbol', { required: 'Symbol required' })}
              className="input pl-9 font-mono"
              placeholder="e.g. RELIANCE, NIFTY24500CE, TCS"
            />
          </div>
          {errors.symbol && <p className="text-xs text-fg-muted mt-1">{errors.symbol.message}</p>}
        </div>

        <div className="grid grid-cols-2 gap-6">
          {/* Side toggle */}
          <div className="card">
            <label className="label mb-3 block">Direction</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setSide('BUY')}
                className={cn(
                  'btn h-12 text-base font-semibold',
                  side === 'BUY' ? 'bg-fg text-bg' : 'border border-border bg-bg-subtle text-fg-muted hover:text-fg'
                )}
              >
                BUY
              </button>
              <button
                type="button"
                onClick={() => setSide('SELL')}
                className={cn(
                  'btn h-12 text-base font-semibold',
                  side === 'SELL' ? 'bg-fg text-bg' : 'border border-border bg-bg-subtle text-fg-muted hover:text-fg'
                )}
              >
                SELL
              </button>
            </div>
          </div>

          {/* Mode toggle */}
          <div className="card">
            <label className="label mb-3 block">Mode</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setMode('paper')}
                className={cn(
                  'btn h-12 text-sm uppercase font-medium tracking-wide',
                  mode === 'paper' ? 'bg-fg text-bg' : 'border border-border bg-bg-subtle text-fg-muted hover:text-fg'
                )}
              >
                Paper
              </button>
              <button
                type="button"
                onClick={() => setMode('live')}
                className={cn(
                  'btn h-12 text-sm uppercase font-medium tracking-wide',
                  mode === 'live' ? 'bg-fg text-bg border-2 border-fg' : 'border border-border bg-bg-subtle text-fg-muted hover:text-fg'
                )}
              >
                Live
              </button>
            </div>
            {mode === 'live' && (
              <div className="mt-3 flex items-start gap-2 text-xs text-fg-muted p-2 border border-border rounded">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <span>Live mode places real orders. Verify before submitting.</span>
              </div>
            )}
          </div>
        </div>

        {/* Order params */}
        <div className="card grid grid-cols-2 gap-4">
          <div>
            <label className="label mb-2 block">Quantity</label>
            <input
              {...register('qty', { required: true, valueAsNumber: true, min: 1 })}
              type="number"
              min={1}
              className="input num"
              placeholder="0"
            />
          </div>
          <div>
            <label className="label mb-2 block">Order Type</label>
            <select {...register('order_type')} className="input">
              <option value="LIMIT">LIMIT</option>
              <option value="MARKET">MARKET</option>
              <option value="SL">Stop-Loss (SL)</option>
              <option value="SL-M">Stop-Loss Market (SL-M)</option>
            </select>
          </div>
          <div>
            <label className="label mb-2 block">Limit Price</label>
            <input
              {...register('limit_price', { valueAsNumber: true })}
              type="number"
              step="0.05"
              className="input num"
              placeholder="0.00"
            />
          </div>
          <div>
            <label className="label mb-2 block">Product</label>
            <select {...register('product')} className="input">
              <option value="MIS">MIS (Intraday)</option>
              <option value="CNC">CNC (Delivery)</option>
              <option value="NRML">NRML (Overnight Margin)</option>
            </select>
          </div>
          <div>
            <label className="label mb-2 block">Stop Loss (optional)</label>
            <input
              {...register('stop_loss', { valueAsNumber: true })}
              type="number"
              step="0.05"
              className="input num"
              placeholder="0.00"
            />
          </div>
          <div>
            <label className="label mb-2 block">Target (optional)</label>
            <input
              {...register('target', { valueAsNumber: true })}
              type="number"
              step="0.05"
              className="input num"
              placeholder="0.00"
            />
          </div>
        </div>

        {/* Cost summary */}
        <div className="card bg-bg-muted">
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <div className="label mb-1">Estimated Cost</div>
              <div className="num text-base">{formatINR(estCost)}</div>
            </div>
            <div>
              <div className="label mb-1">Estimated Charges</div>
              <div className="num text-base">{formatINR(46)}</div>
              <div className="text-2xs text-fg-subtle">₹20 brkr + ₹15 STT + ₹11 GST</div>
            </div>
            <div>
              <div className="label mb-1">Total Outlay</div>
              <div className="num text-base font-semibold">{formatINR(estCost + 46)}</div>
            </div>
          </div>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={placeOrder.isPending}
          className="btn-primary w-full h-12 text-base"
        >
          {placeOrder.isPending ? 'Placing...' : `Place ${side} Order (${mode.toUpperCase()})`}
        </button>
      </form>
    </div>
  );
}
