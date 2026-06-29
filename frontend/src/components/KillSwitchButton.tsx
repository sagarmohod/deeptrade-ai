import { useState } from 'react';
import { Power } from 'lucide-react';
import { toast } from 'sonner';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { endpoints } from '@/api/client';
import { cn } from '@/lib/utils';

export function KillSwitchButton() {
  const [confirming, setConfirming] = useState(false);
  const qc = useQueryClient();

  const { data: status } = useQuery({
    queryKey: ['kill-status'],
    queryFn: endpoints.control.killSwitchStatus,
    refetchInterval: 5_000,
  });

  const activate = useMutation({
    mutationFn: () => endpoints.control.activateKill('manual_via_ui'),
    onSuccess: () => {
      toast.success('Kill switch activated. All trading halted.');
      qc.invalidateQueries({ queryKey: ['kill-status'] });
      setConfirming(false);
    },
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  const reset = useMutation({
    mutationFn: () => endpoints.control.resetKill(),
    onSuccess: () => {
      toast.success('Kill switch reset.');
      qc.invalidateQueries({ queryKey: ['kill-status'] });
    },
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  if (status?.active) {
    return (
      <button
        onClick={() => reset.mutate()}
        className="btn border-2 border-fg bg-bg text-fg font-semibold uppercase tracking-wide text-xs"
      >
        <Power className="w-3.5 h-3.5" />
        Halted — Reset
      </button>
    );
  }

  if (confirming) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-fg-muted uppercase tracking-wide">Confirm?</span>
        <button
          onClick={() => activate.mutate()}
          className="btn bg-fg text-bg uppercase tracking-wide text-xs font-semibold"
        >
          Yes, Halt All
        </button>
        <button
          onClick={() => setConfirming(false)}
          className="btn-ghost text-xs"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setConfirming(true)}
      className={cn(
        'btn border-2 border-border text-fg-muted uppercase tracking-wide text-xs',
        'hover:border-fg hover:text-fg transition-colors'
      )}
      title="Kill switch — halt all trading"
    >
      <Power className="w-3.5 h-3.5" />
      Kill
    </button>
  );
}
