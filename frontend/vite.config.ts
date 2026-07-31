/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          recharts: ["recharts"],
          vendor: ["react", "react-dom", "react-router-dom"],
          analytics: ["./src/components/AnalyticsPanel", "./src/components/DailyAnalyticsPanel"],
          admin: ["./src/components/CentralCommand", "./src/pages/SystemLogs"],
          pages: ["./src/pages/MarketsPage", "./src/pages/WatchlistPage", "./src/pages/PerformancePage"],
        },
      },
    },
    chunkSizeWarningLimit: 500,
    target: "es2020",
    minify: "esbuild",
    cssMinify: true,
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    exclude: ["node_modules", "e2e", "tests/e2e", "**/*.spec.ts"],
    include: ["src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}"],
  },
});
