/** API client — wraps fetch with base URL + error handling. */

const BASE_URL = import.meta.env.VITE_API_BASE || '/api/v1';

class APIError extends Error {
  constructor(public status: number, public body: unknown, message: string) {
    super(message);
    this.name = 'APIError';
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
  });

  const text = await res.text();
  let body: unknown = text;
  try { body = JSON.parse(text); } catch { /* keep as text */ }

  if (!res.ok) {
    const msg = (body as { detail?: string })?.detail || res.statusText;
    throw new APIError(res.status, body, msg);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

// ===== Endpoint helpers =====

export const endpoints = {
  health: () => api.get<{
    status: string;
    mode: string;
    app_name: string;
    env: string;
    live_enabled: boolean;
  }>('/health'),

  signals: {
    list: (params?: { horizon?: string; symbol?: string; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.horizon) q.set('horizon', params.horizon);
      if (params?.symbol) q.set('symbol', params.symbol);
      if (params?.limit) q.set('limit', String(params.limit));
      return api.get<{ signals: Signal[] }>(`/signals/?${q}`);
    },
    top: (limit = 20) => api.get<{ signals: TopSignal[] }>(`/signals/top?limit=${limit}`),
  },

  orders: {
    list: (mode: 'paper' | 'live' | 'all' = 'all') =>
      api.get<{ count: number; orders: Order[] }>(`/orders/?mode=${mode}`),
    today: (mode: 'paper' | 'live' | 'all' = 'paper') =>
      api.get<{ count: number; orders: Order[] }>(`/orders/today?mode=${mode}`),
    history: (mode: 'paper' | 'live' | 'all' = 'paper', days = 30) =>
      api.get<{ count: number; orders: Order[] }>(`/orders/history?mode=${mode}&days=${days}`),
  },

  positions: {
    list: (mode: 'paper' | 'live' | 'all' = 'all', openOnly = true) =>
      api.get<{ positions: Position[] }>(`/positions/?mode=${mode}&open_only=${openOnly}`),
  },

  pnl: {
    summary: (period: string, mode: 'paper' | 'live' | 'compare' = 'compare') =>
      api.get<{ breakdown: Record<string, PnLBreakdown> }>(`/pnl/?period=${period}&mode=${mode}`),
    equityCurve: (days = 30, mode: 'paper' | 'live' | 'both' = 'both') =>
      api.get<{ curves: Record<string, EquityPoint[]> }>(
        `/pnl/daily-equity-curve?days=${days}&mode=${mode}`
      ),
  },

  trading: {
    placeManualOrder: (order: ManualOrderRequest) =>
      api.post<{ ok: boolean; message: string }>('/trading/orders/manual', order),
    autoScalpingStatus: () =>
      api.get<AutoScalpingStatus>('/trading/auto-scalping/status'),
    enableAutoScalping: (settings: AutoScalpingEnableRequest) =>
      api.post<{ ok: boolean; session_id: string }>('/trading/auto-scalping/enable', settings),
    disableAutoScalping: () =>
      api.post<{ ok: boolean }>('/trading/auto-scalping/disable'),
  },

  models: {
    list: (name?: string) =>
      api.get<{ models: ModelVersion[] }>(`/models/${name ? `?name=${name}` : ''}`),
    activate: (name: string, version: string) =>
      api.post<{ ok: boolean }>(`/models/${name}/${version}/activate`),
    rollback: (name: string) =>
      api.post<{ ok: boolean }>(`/models/${name}/rollback`),
  },

  control: {
    killSwitchStatus: () =>
      api.get<{ active: boolean; activated_at?: string; reason?: string }>('/control/kill/status'),
    activateKill: (reason: string) =>
      api.post<{ ok: boolean }>('/control/kill', { confirmation: 'KILL_ALL', reason }),
    resetKill: () =>
      api.post<{ ok: boolean }>('/control/kill/reset'),
  },
};

// ===== Types =====

export interface Signal {
  id: string;
  ts: string;
  symbol: string;
  horizon: string;
  agent: string;
  direction: number;
  confidence: number;
  reasoning: string;
  strategy?: string;
}

export interface TopSignal {
  symbol: string;
  direction: number;
  confidence: number;
  horizon: string;
  ts: string;
}

export interface Order {
  id: string;
  ts_created: string;
  ts_submitted: string | null;
  ts_terminal: string | null;
  mode: string;
  symbol: string;
  exchange: string;
  side: string;
  qty: number;
  order_type: string;
  product: string;
  limit_price: number | null;
  status: string;
  filled_qty: number;
  avg_fill_price: number | null;
  strategy: string | null;
  horizon: string | null;
  broker_order_id: string | null;
  signal_id: string | null;
}

export interface Position {
  id: string;
  symbol: string;
  instrument_type: string;
  side: string;
  qty: number;
  avg_entry: number;
  avg_exit: number | null;
  realized_pnl: number;
  unrealized_pnl: number;
  fees_total: number;
  mode: string;
  horizon: string | null;
  strategy: string | null;
  opened_at: string;
  closed_at: string | null;
  is_open: boolean;
}

export interface PnLBreakdown {
  gross_pnl: number;
  unrealized_pnl: number;
  fees_total: number;
  net_pnl: number;
  n_trades: number;
  n_wins: number;
  n_losses: number;
  hit_rate: number;
}

export interface EquityPoint { ts: string; pnl: number }

export interface ManualOrderRequest {
  symbol: string;
  side: 'BUY' | 'SELL';
  qty: number;
  order_type: 'MARKET' | 'LIMIT' | 'SL' | 'SL-M';
  limit_price?: number;
  trigger_price?: number;
  product: 'MIS' | 'CNC' | 'NRML';
  mode: 'paper' | 'live';
  stop_loss?: number;
  target?: number;
  auto_squareoff?: boolean;
}

export interface PaperScalpingStatus {
  enabled: boolean;
  message?: string;
  trades_executed_today?: number;
  trades_executed_total?: number;
  max_capital_at_risk_total?: number;
}

export interface LiveScalpingStatus {
  enabled: boolean;
  message?: string;
  session_id?: string;
  started_at?: string;
  trades_executed_total?: number;
  trades_executed_today?: number;
  max_total_live_trades?: number;
  max_live_trades_per_day?: number;
  capital_currently_at_risk?: number;
  max_capital_at_risk_total?: number;
  enabled_strategies?: string[];
}

export interface AutoScalpingStatus {
  enabled: boolean;
  paper: PaperScalpingStatus;
  live: LiveScalpingStatus;
}

export interface AutoScalpingEnableRequest {
  max_total_live_trades: number;
  max_live_trades_per_day: number;
  max_concurrent_positions: number;
  max_capital_at_risk_total: number;
  max_capital_per_trade: number;
  broker_balance_min_buffer?: number;
  enabled_strategies: string[];
  confirmation_phrase: string;
}

export interface ModelVersion {
  name: string;
  version: string;
  state: string;
  is_active: boolean;
  trained_at: string | null;
  metrics: Record<string, unknown>;
  horizon: string;
}
