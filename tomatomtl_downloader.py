#!/usr/bin/env python3
import asyncio 
from playwright.async_api import async_playwright 
from playwright_stealth import stealth # Fixed import
from bs4 import BeautifulSoup 
import time 
import sys 
import os 
import re 
import json

DELAY = 3.0 
OUTPUT_FOLDER = "downloaded_novels"
VIDEO_FOLDER = "recordings"

def slugify(text): 
    text = re.sub(r"[^\w\s-]", "", text).strip().lower() 
    return re.sub(r"[\s_-]+", "_", text)

def normalize_url(url): 
    url = url.strip().rstrip("/") 
    match = re.match(r"(https?://(?:www.)?tomatomtl.com/book/[^/]+)", url, re.I) 
    if match: return match.group(1) 
    return url

def get_book_id(url): 
    match = re.search(r"/book/(\d+)", url) 
    return match.group(1) if match else None

async def setup_context(browser):
    """Helper to create a stealthy context with cookies"""
    context = await browser.new_context(
        record_video_dir=VIDEO_FOLDER,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    
    cookies_secret = os.environ.get("TOMATO_COOKIES")
    if cookies_secret:
        try:
            cookies = json.loads(cookies_secret)
            await context.add_cookies(cookies)
            print("✅ Successfully injected cookies from secrets")
        except json.JSONDecodeError:
            print("⚠️ TOMATO_COOKIES secret is not valid JSON. Skipping injection.")
            
    return context

async def get_novel_info(browser, novel_url):
    print(f"\n📖 Fetching novel page: {novel_url}")
    context = await setup_context(browser)
    page = await context.new_page()
    await stealth(page) # Fixed: use stealth() instead of stealth_async()

    try:
        await page.goto(novel_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5) 
        
        title = await page.locator("h1, h2").first.text_content()
        title = (title or "Unknown Novel").strip()
        print(f"✅ Novel title: {title}")
        
        chapter_links = []
        base = "https://tomatomtl.com"
        seen = set()
        
        links = await page.locator("a[href*='/book/']").all()
        for link in links:
            href = await link.get_attribute("href")
            if href:
                if not href.startswith("http"):
                    href = base + href
                if re.search(r"/book/\d+/\d+", href, re.I) and href not in seen:
                    seen.add(href)
                    text = await link.text_content()
                    chapter_links.append({
                        "url": href,
                        "title": (text or f"Chapter {len(chapter_links)+1}").strip()
                    })
        
        print(f"📚 Found {len(chapter_links)} chapters total")
        await context.close()
        return {"title": title, "chapters": chapter_links}
        
    except Exception as e:
        print(f"❌ Error fetching novel info: {e}")
        await context.close()
        return {"title": "Unknown", "chapters": []}

async def fetch_chapter(browser, url):
    context = await setup_context(browser)
    page = await context.new_page()
    await stealth(page) # Fixed: use stealth()

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        
        try:
            await page.wait_for_selector("#chapter_content span.kxa", timeout=15000)
        except:
            print("    ⚠️  Timeout waiting for content. Cloudflare might still be blocking.")
        
        content = await page.evaluate("""() => {
            const article = document.querySelector('#chapter_content');
            if (!article) return '';
            const spans = article.querySelectorAll('span.kxa');
            if (spans.length === 0) return '';
            const texts = [];
            spans.forEach(span => {
                const transtext = span.getAttribute('transtext');
                const orgtext = span.getAttribute('orgtext');
                const text = transtext || orgtext || span.textContent.trim();
                if (text.trim().length > 0) { texts.push(text.trim()); }
            });
            return texts.join('\\n\\n');
        }""")
        
        await context.close()
        return content if content.strip() else "[Could not extract chapter content]"
        
    except Exception as e:
        print(f"    ❌ Error fetching chapter: {e}")
        await context.close()
        return f"[Error: {e}]"

async def download_novel(raw_url, start_chapter=1, end_chapter=None):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    os.makedirs(VIDEO_FOLDER, exist_ok=True)
    novel_url = normalize_url(raw_url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) 
        
        try:
            info = await get_novel_info(browser, novel_url)
            title = info["title"] or "novel"
            chapters = info["chapters"]
            
            if not chapters:
                print("❌ No chapters found! Check your cookies or the URL.")
                return
            
            total = len(chapters)
            start = max(1, start_chapter) - 1
            end = min(end_chapter, total) if end_chapter else total
            selected = chapters[start:end]
            
            safe_title = slugify(title) or "novel"
            filename = os.path.join(OUTPUT_FOLDER, f"{safe_title}_ch{start+1}_to_{end}.txt")
            
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"{title}\n{'='*max(len(title),1)}\n\n")
                for i, ch in enumerate(selected, start+1):
                    print(f"  [{i}/{end}] {ch['title']}")
                    f.write(f"\n{'─'*60}\n{ch['title']}\n{'─'*60}\n\n")
                    content = await fetch_chapter(browser, ch["url"])
                    f.write(content + "\n\n")
                    await asyncio.sleep(DELAY)
            
            print(f"\n✅ Done! Saved to: {filename}")
        finally:
            await browser.close()

async def main():
    if len(sys.argv) < 2:
        sys.exit(1)
    url = sys.argv[1]
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    end = int(sys.argv[3]) if len(sys.argv) > 3 else None
    await download_novel(url, start, end)

if __name__ == "__main__":
    asyncio.run(main())
