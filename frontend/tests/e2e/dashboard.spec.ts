import { test, expect } from '@playwright/test';

test.describe('Dashboard End-to-End Workflows', () => {
  test('User can trigger a full market scan and see the progress tracker', async ({ page }) => {
    // Navigate to the local dashboard
    await page.goto('http://localhost:5173');
    
    // Verify initial state
    await expect(page.getByText('Ready for the next scan')).toBeVisible();
    
    // Trigger Scan
    const runScanButton = page.getByRole('button', { name: /Run full NIFTY 500 scan/i });
    if (await runScanButton.isVisible()) {
      await runScanButton.click();
    } else {
      // Fallback for different label
      await page.getByRole('button', { name: /Run scan/i }).click();
    }
    
    // The new Multi-Agent Tracker should appear instantly
    await expect(page.getByText('Multi-Agent Scanner Active')).toBeVisible();
    
    // Verify individual agent tracking elements
    await expect(page.getByText('Technical Analysis Agent')).toBeVisible();
    await expect(page.getByText('Fundamental Analysis Agent')).toBeVisible();
    await expect(page.getByText('News & Sentiment Agent')).toBeVisible();
    await expect(page.getByText('Backtest Engine')).toBeVisible();
    
    // Wait for scan to complete and table to appear
    // This could take up to 30-60 seconds depending on backend mock
    await expect(page.locator('.candidate-table')).toBeVisible({ timeout: 60000 });
    
    // Verify System Alpha Card is visible
    await expect(page.getByText('System Alpha Overview')).toBeVisible();
    
    // Verify Regime Badge exists in table
    const tableHtml = await page.locator('.candidate-table').innerHTML();
    expect(tableHtml).toMatch(/CATALYST|STANDARD/);
  });
});
