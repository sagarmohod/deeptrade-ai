import { Routes, Route } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { Dashboard } from '@/pages/Dashboard';
import { ManualTrade } from '@/pages/ManualTrade';
import { AutoScalping } from '@/pages/AutoScalping';
import { Orders } from '@/pages/Orders';
import { Signals } from '@/pages/Signals';
import { PnL } from '@/pages/PnL';
import { Compare } from '@/pages/Compare';
import { Models } from '@/pages/Models';
import { Backtests } from '@/pages/Backtests';
import { Settings } from '@/pages/Settings';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="manual-trade" element={<ManualTrade />} />
        <Route path="auto-scalping" element={<AutoScalping />} />
        <Route path="orders" element={<Orders />} />
        <Route path="signals" element={<Signals />} />
        <Route path="pnl" element={<PnL />} />
        <Route path="compare" element={<Compare />} />
        <Route path="models" element={<Models />} />
        <Route path="backtests" element={<Backtests />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
