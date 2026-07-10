import React from 'react';
import { ThemeToggle } from './ThemeToggle';
import { BullIllustration } from './BullIllustration';
import { useTheme } from '../hooks/useTheme';

interface AuthLayoutProps {
  children: React.ReactNode;
}

/**
 * Single form tree for both mobile and desktop.
 * (Previously children were rendered twice — desktop + mobile — which broke
 * Playwright strict locators and could confuse password managers / a11y.)
 */
export const AuthLayout: React.FC<AuthLayoutProps> = ({ children }) => {
  const { theme } = useTheme();

  return (
    <div className={`relative min-h-screen w-full overflow-x-hidden text-gray-900 dark:text-white font-sans ${theme}`}>
      {/* Background images */}
      <div
        className={`fixed inset-0 bg-cover bg-center bg-no-repeat transition-opacity duration-500 ease-out ${
          theme === 'light' ? 'opacity-100' : 'opacity-0'
        }`}
        style={{ backgroundImage: "url('/Light_mode.png')" }}
        aria-hidden="true"
      />
      <div
        className={`fixed inset-0 bg-cover bg-center bg-no-repeat transition-opacity duration-500 ease-out ${
          theme === 'dark' ? 'opacity-100' : 'opacity-0'
        }`}
        style={{ backgroundImage: "url('/Dark_mode.png')" }}
        aria-hidden="true"
      />
      <div className="fixed inset-0 bg-white/10 transition-colors duration-500 dark:bg-slate-950/45" aria-hidden="true" />

      {/* Theme Toggle */}
      <header className="fixed right-4 top-4 z-30 sm:right-6 sm:top-6">
        <ThemeToggle />
      </header>

      <div className="relative z-10 flex min-h-screen w-full flex-col lg:flex-row">
        {/* Branding — compact on mobile, left panel on desktop */}
        <div className="flex flex-col items-center px-5 pt-16 pb-2 lg:w-1/2 lg:items-start lg:justify-between lg:p-12">
          <div className="z-10 w-full lg:mb-0">
            <div className="mb-5 flex items-center justify-center space-x-2 text-xl font-bold lg:mb-16 lg:justify-start lg:text-2xl">
              <svg className="h-7 w-7 text-blue-600 dark:text-blue-500 lg:h-8 lg:w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
              <span>TradeX</span>
            </div>

            <div className="mb-5 animate-[bullFadeIn_0.6s_ease-out] lg:hidden">
              <BullIllustration size={200} className="mx-auto md:hidden" />
              <BullIllustration size={240} className="mx-auto hidden md:flex" />
            </div>

            <div className="hidden lg:block">
              <h1 className="mb-4 text-5xl font-extrabold leading-tight tracking-tight">
                Trade Smarter <br />
                <span className="text-blue-600 dark:text-green-500">Invest Better</span>
              </h1>
              <p className="max-w-md text-lg text-gray-600 dark:text-gray-300">
                Real-time market data at your fingertips
              </p>
            </div>
          </div>

          <div className="z-10 mt-8 hidden w-full flex-wrap gap-4 lg:flex">
            <div className="flex items-center space-x-2 rounded-lg border border-gray-200 bg-white px-4 py-2 backdrop-blur-sm dark:border-gray-700 dark:bg-gray-800/80">
              <svg className="h-5 w-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <div>
                <div className="text-sm font-semibold">Real-time Data</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Live market updates</div>
              </div>
            </div>
            <div className="flex items-center space-x-2 rounded-lg border border-gray-200 bg-white px-4 py-2 backdrop-blur-sm dark:border-gray-700 dark:bg-gray-800/80">
              <svg className="h-5 w-5 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              <div>
                <div className="text-sm font-semibold">Smart Analytics</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Track, analyze & grow</div>
              </div>
            </div>
            <div className="flex items-center space-x-2 rounded-lg border border-gray-200 bg-white px-4 py-2 backdrop-blur-sm dark:border-gray-700 dark:bg-gray-800/80">
              <svg className="h-5 w-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              <div>
                <div className="text-sm font-semibold">Secure & Reliable</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Bank level security</div>
              </div>
            </div>
          </div>
        </div>

        {/* Form — single mount for all breakpoints */}
        <div className="flex flex-1 items-start justify-center px-5 pb-8 pt-2 lg:w-1/2 lg:items-center lg:p-12">
          <div className="w-full max-w-md">
            <div className="rounded-xl border border-white/40 bg-white/[0.75] px-5 py-6 shadow-lg shadow-slate-950/5 backdrop-blur-md transition-colors duration-300 dark:border-white/5 dark:bg-slate-950/60 dark:shadow-black/20 sm:rounded-2xl sm:px-7 sm:py-8 md:px-8 lg:border-white/70 lg:bg-white/[0.82] lg:shadow-xl lg:shadow-slate-950/10 dark:lg:border-white/10 dark:lg:bg-slate-950/70 dark:lg:shadow-2xl dark:lg:shadow-black/30">
              {children}
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes bullFadeIn {
          0% { opacity: 0; transform: scale(0.85); }
          100% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
};
