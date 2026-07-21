import asyncio
import os
from playwright.async_api import async_playwright

# Configuration
TARGET_URL = os.getenv("TARGET_URL", "https://example.com")
SCREENSHOT_DIR = "debug_screenshots"
LOG_DIR = "debug_logs"

async def main():
    # Ensure directories exist
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    async with async_playwright() as p:
        print(f"🚀 Launching browser to visit: {TARGET_URL}")
        
        # Launching a real Chromium browser
        browser = await p.chromium.launch(headless=True) 
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Capture console logs
        page.on("console", lambda msg: print(f"[Browser Console] {msg.text}"))
        page.on("pageerror", lambda err: print(f"[JS Error] {err}"))

        try:
            print("🌐 Navigating to page...")
            # Using 'domcontentloaded' as it is more reliable than 'networkidle'
            response = await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            print(f"📍 Current URL: {page.url}")
            print(f"📊 Response Status: {response.status if response else 'No Response'}")

            # 1. Screenshot immediately after load
            await page.screenshot(path=f"{SCREENSHOT_DIR}/1_after_load.png", full_page=True)
            
            # 2. Wait a bit for any JavaScript/Cloudflare challenges to run
            print("⏳ Waiting 10 seconds for any JS execution...")
            await asyncio.sleep(10)
            await page.screenshot(path=f"{SCREENSHOT_DIR}/2_after_delay.png", full_page=True)

            # 3. Save the full HTML source
            content = await page.content()
            with open(f"{LOG_DIR}/page_source.html", "w", encoding="utf-8") as f:
                f.write(content)
            
            # 4. Save the final URL in case of redirects
            with open(f"{LOG_DIR}/final_url.txt", "w", encoding="utf-8") as f:
                f.write(page.url)

            print("\n✅ Debugging complete. Check the GitHub Artifacts for screenshots and HTML.")

        except Exception as e:
            print(f"❌ An error occurred: {e}")
            # Take a screenshot even on failure to see the error page
            try:
                await page.screenshot(path=f"{SCREENSHOT_DIR}/error_state.png", full_page=True)
            except:
                pass

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
