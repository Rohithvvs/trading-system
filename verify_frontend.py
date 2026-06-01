import asyncio
from playwright.async_api import async_playwright
import time

async def main():
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("Navigating to dashboard...")
        await page.goto("http://127.0.0.1:5174/")
        
        # Wait for the network to be somewhat idle
        await page.wait_for_load_state("networkidle")
        
        # Give it a few seconds to render live data
        time.sleep(5)
        
        # Extract the HTML or specific data
        content = await page.content()
        
        # Print a summary of the page text
        text = await page.evaluate("document.body.innerText")
        print("\n--- PAGE TEXT ---")
        print(text[:2000])  # Print first 2000 chars
        print("--- END PAGE TEXT ---\n")
        
        # Look for specific dashboard elements
        api_health = await page.evaluate("Array.from(document.querySelectorAll('*')).find(el => el.textContent.includes('API Health'))?.textContent || 'NOT FOUND'")
        fyers_status = await page.evaluate("Array.from(document.querySelectorAll('*')).find(el => el.textContent.includes('FYERS'))?.textContent || 'NOT FOUND'")
        
        print("API Health element:", api_health)
        print("FYERS element:", fyers_status)
        
        await browser.close()
        print("Done verification!")

if __name__ == "__main__":
    asyncio.run(main())
