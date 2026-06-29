import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type Theme = 'light' | 'dark' | 'system';

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

export const useTheme = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'system',
      setTheme: (theme) => {
        set({ theme });
        applyTheme(theme);
      },
      toggleTheme: () => {
        const current = get().theme;
        const next = current === 'dark' ? 'light' : 'dark';
        set({ theme: next });
        applyTheme(next);
      },
    }),
    { name: 'deeptrade-theme' }
  )
);

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === 'system') {
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.classList.toggle('dark', isDark);
  } else {
    root.classList.toggle('dark', theme === 'dark');
  }
}

// Apply theme on initial load
if (typeof window !== 'undefined') {
  const stored = localStorage.getItem('deeptrade-theme');
  if (stored) {
    try {
      const { state } = JSON.parse(stored);
      applyTheme(state.theme);
    } catch {
      applyTheme('system');
    }
  } else {
    applyTheme('system');
  }

  // Listen for system theme changes
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const stored = localStorage.getItem('deeptrade-theme');
    if (stored) {
      try {
        const { state } = JSON.parse(stored);
        if (state.theme === 'system') applyTheme('system');
      } catch {
        // ignore
      }
    }
  });
}
