import { useQuery } from '@tanstack/react-query';
import { endpoints } from '@/api/client';

export function Settings() {
  const { data: health } = useQuery({
    queryKey: ['health-detail'],
    queryFn: endpoints.health,
  });

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>

      <div className="card space-y-4">
        <h2 className="font-medium">System</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <Row label="App" value={health?.app_name ?? '—'} />
          <Row label="Mode" value={health?.mode ?? '—'} />
          <Row label="Environment" value={health?.env ?? '—'} />
          <Row label="Live trading" value={health?.live_enabled ? 'Enabled' : 'Disabled'} />
        </div>
      </div>

      <div className="card space-y-4">
        <h2 className="font-medium">Zerodha Connection</h2>
        <p className="text-sm text-fg-muted">
          Daily authentication required. Click below to log in via Kite Connect.
        </p>
        <a href="/api/v1/auth/kite/login-url" target="_blank"
           className="btn-secondary inline-flex">
          Get Kite login URL
        </a>
      </div>

      <div className="card space-y-4">
        <h2 className="font-medium">Capital Limits</h2>
        <p className="text-sm text-fg-muted">
          Configure via auto-scalping page. Per-trade and total caps are enforced by the risk engine.
        </p>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="label mb-1">{label}</div>
      <div className="text-sm">{value}</div>
    </div>
  );
}
