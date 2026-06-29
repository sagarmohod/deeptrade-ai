import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, RotateCcw } from 'lucide-react';
import { endpoints } from '@/api/client';
import { cn, formatDateTime } from '@/lib/utils';

export function Models() {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['models'],
    queryFn: () => endpoints.models.list(),
  });

  const activate = useMutation({
    mutationFn: ({ name, version }: { name: string; version: string }) =>
      endpoints.models.activate(name, version),
    onSuccess: () => {
      toast.success('Model activated');
      qc.invalidateQueries({ queryKey: ['models'] });
    },
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  const rollback = useMutation({
    mutationFn: (name: string) => endpoints.models.rollback(name),
    onSuccess: () => {
      toast.success('Rolled back to previous version');
      qc.invalidateQueries({ queryKey: ['models'] });
    },
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Models</h1>

      <div className="card p-0 overflow-hidden">
        {isLoading ? (
          <div className="text-sm text-fg-subtle text-center py-12">Loading…</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th className="px-4">Name</th>
                <th>Version</th>
                <th>Horizon</th>
                <th>State</th>
                <th>Trained</th>
                <th>Composite Score</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data?.models?.map((m) => (
                <tr key={`${m.name}_${m.version}`}>
                  <td className="px-4 font-medium">{m.name}</td>
                  <td className="font-mono text-xs">{m.version}</td>
                  <td><span className="badge-outline uppercase">{m.horizon}</span></td>
                  <td>
                    <span className={cn('badge', m.is_active ? 'badge-strong' : 'badge-default')}>
                      {m.is_active && <Check className="w-3 h-3 mr-1" />}
                      {m.state}
                    </span>
                  </td>
                  <td className="text-fg-muted text-xs">
                    {m.trained_at ? formatDateTime(m.trained_at) : '—'}
                  </td>
                  <td className="num">
                    {(m.metrics as { composite_score?: number })?.composite_score?.toFixed(3) ?? '—'}
                  </td>
                  <td className="px-4">
                    <div className="flex gap-2 justify-end">
                      {!m.is_active && m.state !== 'DEPRECATED' && (
                        <button
                          onClick={() => activate.mutate({ name: m.name, version: m.version })}
                          className="btn-secondary text-xs"
                        >
                          Activate
                        </button>
                      )}
                      {m.is_active && (
                        <button
                          onClick={() => rollback.mutate(m.name)}
                          className="btn-ghost text-xs"
                          title="Rollback to previous"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {!data?.models?.length && (
                <tr>
                  <td colSpan={7} className="text-center text-fg-subtle py-12">
                    No models registered. Train one with <code className="font-mono bg-bg-muted px-1.5 py-0.5 rounded">make train</code>.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
