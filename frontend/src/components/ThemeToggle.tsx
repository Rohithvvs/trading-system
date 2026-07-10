import React from 'react';
import { useTheme } from '../hooks/useTheme';

export const ThemeToggle: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === 'dark';

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="group inline-flex h-10 items-center gap-2 rounded-full border border-white/20 bg-white/70 px-2 text-xs font-semibold text-slate-700 shadow-lg shadow-slate-950/10 backdrop-blur-md transition-all duration-300 hover:border-blue-400/50 hover:bg-white/90 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-transparent dark:border-white/10 dark:bg-slate-950/60 dark:text-slate-200 dark:shadow-black/30 dark:hover:border-emerald-400/50 dark:hover:bg-slate-900/75"
      aria-label={`Switch to ${isDark ? 'light' : 'dark'} theme`}
      role="switch"
      aria-checked={isDark}
      title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
    >
      <span className="sr-only">{isDark ? 'Dark mode active' : 'Light mode active'}</span>
      <span className="relative flex h-6 w-11 shrink-0 items-center rounded-full bg-slate-300 p-0.5 transition-colors duration-300 dark:bg-slate-700">
        <span
          className={`flex h-5 w-5 items-center justify-center rounded-full bg-white text-slate-700 shadow-sm transition-transform duration-300 dark:bg-slate-950 dark:text-emerald-300 ${
            isDark ? 'translate-x-5' : 'translate-x-0'
          }`}
          aria-hidden="true"
        >
          {isDark ? (
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 12.8A8.5 8.5 0 1111.2 3 6.5 6.5 0 0021 12.8z" />
            </svg>
          ) : (
            <svg className="h-3.5 w-3.5 text-amber-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.36-6.36l-1.42 1.42M7.06 16.94l-1.42 1.42m12.72 0l-1.42-1.42M7.06 7.06L5.64 5.64" />
              <circle cx="12" cy="12" r="4" />
            </svg>
          )}
        </span>
      </span>
      <span className="min-w-[4.5rem] text-left transition-colors duration-300">
        {isDark ? 'Dark' : 'Light'}
      </span>
    </button>
  );
};
