#!/usr/bin/env python3
"""
Tomato MTL Novel Chapter Downloader with Playwright
- Handles React SPA + Cloudflare protection
- Executes JavaScript to render span.kxa elements
- Extracts English translations (transtext attribute)
"""

import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import time
import sys
import os
import re
import json

DELAY = 3.0
OUTPUT_FOLDER = "downloaded_novels"


def slugify(text):
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "_", text)


def normalize_url(url):
    url = url.strip().rstrip("/")
    match = re.match(r"(https?://(?:www\.)?tomatomtl\.com/book/[^/]+)", url, re.I)
    if match:
        return match.group(1)
    return url


def get_book_id(url):
    match = re.search(r"/book/(\d+)", url)
    return match.group(1) if match else None


async def get_novel_info(browser, novel_url):
    """Fetch novel info and chapter list using Playwright"""
    print(f"\n📖 Fetching novel page: {novel_url}")
    
    context = await browser.new_context()
    page = await context.new_page()
    
    try:
        await page.goto(novel_url, wait_until="networkidle", timeout=30000)
        print(f"   ✅ Page loaded")
        
        # Get title
        title = await page.locator("h1, h2").first.text_content()
        title = (title or "Unknown Novel").strip()
        print(f"✅ Novel title: {title}")
        
        book_id = get_book_id(novel_url)
        print(f"📘 Book ID: {book_id}")
        
        # Extract chapter links from the page
        chapter_links = []
        base = "https://tomatomtl.com"
        seen = set()
        
        # Get all chapter links
        links = await page.locator("a[href*='/book/']").all()
        for link in links:
            href = await link.get_attribute("href")
            if href:
                if not href.startswith("http"):
                    href = base + href
                # Look for /book/ID/CHAPTER_ID pattern
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
    """Fetch and extract chapter content using Playwright"""
    context = await browser.new_context()
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        
        # Wait for chapter content to render
        try:
            await page.wait_for_selector("#chapter_content span.kxa", timeout=10000)
        except:
            print("    ⚠️  Timeout waiting for content to render")
        
        # Extract content from the rendered page
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
                if (text.trim().length > 0) {
                    texts.push(text.trim());
                }
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
    """Main download function"""
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    novel_url = normalize_url(raw_url)
    
    async with async_playwright() as p:
        # Use chromium browser
        browser = await p.chromium.launch(headless=True)
        
        try:
            info = await get_novel_info(browser, novel_url)
            title = info["title"] or "novel"
            chapters = info["chapters"]
            
            if not chapters:
                print("❌ No chapters found!")
                return
            
            total = len(chapters)
            start = max(1, start_chapter) - 1
            end = min(end_chapter, total) if end_chapter else total
            selected = chapters[start:end]
            
            print(f"\n📌 Downloading chapters {start+1} to {end} (out of {total} total)")
            
            safe_title = slugify(title) or "novel"
            filename = os.path.join(OUTPUT_FOLDER, f"{safe_title}_ch{start+1}_to_{end}.txt")
            print(f"💾 Saving to: {filename}\n{'─'*50}")
            
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"{title}\n{'='*max(len(title),1)}\n")
                f.write(f"Chapters: {start+1} to {end}\n")
                f.write(f"Source: {novel_url}\n\n\n")
                
                for i, ch in enumerate(selected, start+1):
                    ch_title = ch["title"] or f"Chapter {i}"
                    print(f"  [{i}/{end}] {ch_title}")
                    
                    f.write(f"\n{'─'*60}\n{ch_title}\n{'─'*60}\n\n")
                    
                    content = await fetch_chapter(browser, ch["url"])
                    f.write(content + "\n\n")
                    
                    await asyncio.sleep(DELAY)
            
            print(f"\n✅ Done! Saved to: {os.path.abspath(filename)}")
            
        finally:
            await browser.close()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python tomatomtl_downloader.py <url> [start] [end]")
        sys.exit(1)
    
    url = sys.argv[1]
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    end = int(sys.argv[3]) if len(sys.argv) > 3 else None
    
    await download_novel(url, start, end)


if __name__ == "__main__":
    asyncio.run(main())
