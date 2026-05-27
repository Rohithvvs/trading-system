import { test, expect } from '@playwright/test';

test.describe('Scanner UI End-to-End Flow', () => {
  test('User clicks scanner, loads recommendations, and indicators are visible', async ({ page }) => {
    // Navigate to the dashboard or scanner page
    await page.goto('http://localhost:5173');

    // Assuming there's a button or link to open the scanner
    const scannerLink = page.getByRole('link', { name: /scanner/i });
    if (await scannerLink.isVisible()) {
      await scannerLink.click();
    }
    
    // Wait for the scanner to complete loading
    // Adjust selector based on actual frontend loading state (e.g. spinner or progress bar)
    await expect(page.locator('text=/loading|scanning/i')).toHaveCount(0, { timeout: 30000 });

    // Verify recommendation rows or cards are rendered
    // Usually these might have a specific test ID or class
    const recommendationCards = page.locator('.recommendation-card, [data-testid="recommendation-card"], table tr');
    
    // Check if empty state is legitimately shown OR recommendations are rendered
    const emptyState = page.locator('text=/No recommendations found/i');
    const hasRecommendations = (await recommendationCards.count()) > 0;
    const hasEmptyState = await emptyState.isVisible();

    // Must have one or the other
    expect(hasRecommendations || hasEmptyState).toBeTruthy();

    if (hasRecommendations) {
      // If we have recommendations, indicators must be visible and NOT NaN
      const firstCard = recommendationCards.first();
      await expect(firstCard).toBeVisible();

      const cardText = await firstCard.innerText();
      expect(cardText).not.toMatch(/NaN/);
      expect(cardText).not.toMatch(/undefined/);
      
      // Ensure key indicators are likely rendered
      // E.g., looking for numbers or technical terms
      expect(cardText.length).toBeGreaterThan(10);
    }
  });
});
