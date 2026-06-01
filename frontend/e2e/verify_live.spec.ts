import { test, expect } from '@playwright/test';

test('Live Dashboard Verification', async ({ page }) => {
  page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));
  page.on('pageerror', error => console.log('BROWSER ERROR:', error.message));

  console.log('Navigating to Live Dashboard...');
  await page.goto('http://127.0.0.1:5174/');
  
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(5000);
  
  await page.screenshot({ path: 'dashboard.png', fullPage: true });
  
  const text = await page.evaluate(() => document.body.innerText);
  console.log('\n--- PAGE TEXT ---');
  console.log(text);
  console.log('--- END PAGE TEXT ---\n');

  const html = await page.content();
  console.log('\n--- PAGE HTML ---');
  console.log(html.substring(0, 1000));
  console.log('--- END PAGE HTML ---\n');
});
