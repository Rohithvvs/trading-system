import React from 'react';
import { ThemeToggle } from './ThemeToggle';
import { BullIllustration } from './BullIllustration';
import { useTheme } from '../hooks/useTheme';

interface AuthLayoutProps {
  children: React.ReactNode;
}

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

      {/* ===== DESKTOP LAYOUT (unchanged) ===== */}
      <div className="hidden lg:flex relative z-10 min-h-screen w-full">
        {/* Left Branding Area */}
        <div className="w-1/2 relative overflow-hidden flex-col justify-between p-12 items-start flex">
          <div className="z-10 w-full">
            <div className="flex items-center space-x-2 text-2xl font-bold mb-16">
              <svg className="w-8 h-8 text-blue-600 dark:text-blue-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
              <span>TradeX</span>
            </div>

            <h1 className="text-5xl font-extrabold tracking-tight mb-4 leading-tight">
              Trade Smarter <br/>
              <span className="text-blue-600 dark:text-green-500">Invest Better</span>
            </h1>
            <p className="text-lg text-gray-600 dark:text-gray-300 max-w-md">
              Real-time market data at your fingertips
            </p>
          </div>

          {/* Features Chips */}
          <div className="z-10 w-full flex flex-wrap gap-4 mt-8">
            <div className="flex items-center space-x-2 bg-white dark:bg-gray-800/80 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 backdrop-blur-sm">
              <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <div>
                <div className="text-sm font-semibold">Real-time Data</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Live market updates</div>
              </div>
            </div>
            <div className="flex items-center space-x-2 bg-white dark:bg-gray-800/80 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 backdrop-blur-sm">
              <svg className="w-5 h-5 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              <div>
                <div className="text-sm font-semibold">Smart Analytics</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Track, analyze & grow</div>
              </div>
            </div>
            <div className="flex items-center space-x-2 bg-white dark:bg-gray-800/80 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 backdrop-blur-sm">
              <svg className="w-5 h-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              <div>
                <div className="text-sm font-semibold">Secure & Reliable</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Bank level security</div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Form Area */}
        <div className="w-1/2 flex items-center justify-center p-12">
          <div className="w-full max-w-md">
            <div className="rounded-2xl border border-white/70 bg-white/[0.82] p-8 shadow-xl shadow-slate-950/10 backdrop-blur-xl transition-colors duration-300 dark:border-white/10 dark:bg-slate-950/70 dark:shadow-2xl dark:shadow-black/30">
              {children}
            </div>
          </div>
        </div>
      </div>

      {/* ===== MOBILE / TABLET LAYOUT ===== */}
      <div className="flex lg:hidden relative z-10 min-h-screen flex-col">
        <div className="flex-1 flex flex-col items-center justify-start px-5 pt-16 pb-8 safe-area-bottom">
          {/* TradeX Logo */}
          <div className="flex items-center space-x-2 text-xl font-bold mb-5">
            <svg className="w-7 h-7 text-blue-600 dark:text-blue-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
            <span>TradeX</span>
          </div>

          {/* Bull Illustration */}
          <div className="mb-5 animate-[bullFadeIn_0.6s_ease-out]">
            <BullIllustration
              size={200}
              className="mx-auto md:hidden"
            />
            <BullIllustration
              size={240}
              className="mx-auto hidden md:flex lg:hidden"
            />
          </div>

          {/* Form Card */}
          <div className="w-full max-w-md">
            <div className="rounded-xl border border-white/40 bg-white/[0.75] px-5 py-6 shadow-lg shadow-slate-950/5 backdrop-blur-md transition-colors duration-300 dark:border-white/5 dark:bg-slate-950/60 dark:shadow-black/20 sm:rounded-2xl sm:px-7 sm:py-8 md:px-8 md:py-8">
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
        .safe-area-bottom {
          padding-bottom: env(safe-area-inset-bottom, 1rem);
        }
      `}</style>
    </div>
  );
};
