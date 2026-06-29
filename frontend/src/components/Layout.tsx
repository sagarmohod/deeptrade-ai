import { NavLink, Outlet } from 'react-router-dom';
import {
  Activity, BrainCircuit, ClipboardList, Cog, FlaskConical, GitCompare,
  LayoutDashboard, LineChart, Moon, Sun, TrendingUp, Wallet, Zap, Monitor,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTheme } from '@/stores/theme';
import { cn } from '@/lib/utils';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { endpoints } from '@/api/client';
import { KillSwitchButton } from './KillSwitchButton';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/manual-trade', icon: TrendingUp, label: 'Manual Trade' },
  { to: '/auto-scalping', icon: Zap, label: 'Auto Scalping' },
  { to: '/orders', icon: ClipboardList, label: 'Orders' },
  { to: '/signals', icon: Activity, label: 'Signals' },
  { to: '/pnl', icon: Wallet, label: 'P&L' },
  { to: '/compare', icon: GitCompare, label: 'Compare' },
  { to: '/models', icon: BrainCircuit, label: 'Models' },
  { to: '/backtests', icon: FlaskConical, label: 'Backtests' },
  { to: '/settings', icon: Cog, label: 'Settings' },
];

export function Layout() {
  const { theme, setTheme } = useTheme();
  const queryClient = useQueryClient();
  const [engineAlive, setEngineAlive] = useState(false);
  const engineTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: endpoints.health,
    refetchInterval: 30_000,
  });

  // Real-time updates via SSE — runs globally regardless of which page is active
  useEffect(() => {
    const base = import.meta.env.VITE_API_BASE || '/api/v1';
    const es = new EventSource(`${base}/stream/all`);

    const markAlive = () => {
      setEngineAlive(true);
      if (engineTimerRef.current) clearTimeout(engineTimerRef.current);
      // If no heartbeat for 90s (1.5× tick interval), mark engine as offline
      engineTimerRef.current = setTimeout(() => setEngineAlive(false), 90_000);
    };

    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data) as { type: string };
        if (evt.type === 'heartbeat') {
          markAlive();
        } else if (evt.type === 'order') {
          markAlive();
          queryClient.invalidateQueries({ queryKey: ['orders'] });
          queryClient.invalidateQueries({ queryKey: ['positions'] });
        } else if (evt.type === 'signal') {
          markAlive();
          queryClient.invalidateQueries({ queryKey: ['signals'] });
        }
      } catch { /* ignore malformed events */ }
    };

    return () => {
      es.close();
      if (engineTimerRef.current) clearTimeout(engineTimerRef.current);
    };
  }, [queryClient]);

  return (
    <div className="min-h-screen bg-bg text-fg flex">
      {/* Sidebar */}
      <aside className="w-56 border-r border-border bg-bg-subtle flex flex-col">
        <div className="px-4 py-5 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md bg-fg flex items-center justify-center">
              <LineChart className="w-4 h-4 text-bg" />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight">DeepTrade AI</div>
              <div className="text-2xs text-fg-subtle">v0.1.0</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-2 space-y-0.5">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                  isActive
                    ? 'bg-fg text-bg font-medium'
                    : 'text-fg-muted hover:bg-bg-muted hover:text-fg'
                )
              }
            >
              <item.icon className="w-4 h-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-border space-y-2">
          <div className="flex items-center justify-between px-2">
            <span className="text-xs text-fg-subtle">Theme</span>
            <div className="flex border border-border rounded-md overflow-hidden">
              <button
                onClick={() => setTheme('light')}
                className={cn(
                  'p-1.5 transition-colors',
                  theme === 'light' ? 'bg-fg text-bg' : 'text-fg-muted hover:text-fg'
                )}
                aria-label="Light mode"
              >
                <Sun className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setTheme('dark')}
                className={cn(
                  'p-1.5 transition-colors border-l border-border',
                  theme === 'dark' ? 'bg-fg text-bg' : 'text-fg-muted hover:text-fg'
                )}
                aria-label="Dark mode"
              >
                <Moon className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setTheme('system')}
                className={cn(
                  'p-1.5 transition-colors border-l border-border',
                  theme === 'system' ? 'bg-fg text-bg' : 'text-fg-muted hover:text-fg'
                )}
                aria-label="System theme"
              >
                <Monitor className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-14 border-b border-border bg-bg flex items-center justify-between px-6 sticky top-0 z-10">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="status-dot bg-fg pulse-subtle" />
              <span className="text-sm font-medium uppercase tracking-wide">
                {health?.mode || 'unknown'}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span
                className={cn(
                  'w-2 h-2 rounded-full',
                  engineAlive ? 'bg-green-500' : 'bg-fg-subtle'
                )}
                title={engineAlive ? 'Paper engine running' : 'Engine offline or market closed'}
              />
              <span className="text-xs text-fg-subtle">
                {engineAlive ? 'Engine ON' : 'Engine OFF'}
              </span>
            </div>
            <div className="text-sm text-fg-muted">
              {new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })} IST
            </div>
          </div>

          <div className="flex items-center gap-3">
            <KillSwitchButton />
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto">
          <div className="p-6 max-w-[1600px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
