/**
 * Scanner page — reuses the existing production App scanner workflow.
 * Mounted at /scanner with full backend screener integration.
 */
import App from "../../App";

export function ScannerPage() {
  return <App forcedView="scanner" embedMode />;
}
