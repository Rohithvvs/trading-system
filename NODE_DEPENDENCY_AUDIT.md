# NODE DEPENDENCY AUDIT

## Overall Requirements
- **Node.js Version Required**: Node v18+ (due to Vite 5 and modern React hooks).
- **Package Manager**: `npm` (v9+ recommended).
- **TypeScript**: `^5.8.3`

## Core Packages Identified
### Runtime Dependencies
- `react`: `^18.3.1`
- `react-dom`: `^18.3.1`
- `react-router-dom`: `^7.15.1`
- `recharts`: `^2.15.4`

### Build & Dev Dependencies
- `vite`: `^5.4.19`
- `@vitejs/plugin-react`: `^4.3.4`
- `tailwindcss`: `^3.4.19`
- `postcss`: `^8.5.15`
- `autoprefixer`: `^10.5.0`
- `vitest`: `^4.1.7`
- `@playwright/test`: `^1.52.0`

## Findings
- **Missing Packages**: None actively breaking compilation, but `lucide-react` or similar icon libraries are often used in such dashboards. If standard HTML/CSS is used, no further dependencies are required.
- **Build vs Runtime**: All runtime components correctly sit under `dependencies`. Vite and TS reside correctly in `devDependencies`.
- **E2E Tooling**: The Playwright scripts (`e2e` npm run command) reference a powershell script (`../scripts/run-e2e.ps1`). This fundamentally breaks cross-platform compatibility on Linux CI/CD pipelines (Ubuntu servers) where `.ps1` execution is unsupported natively.

## Severity: MEDIUM
The hardcoded PowerShell script in `package.json` (`npm run e2e`) breaks Linux testing pipelines natively.
