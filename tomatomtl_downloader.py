#!/usr/bin/env python3
"""
Tomato MTL Novel Chapter Downloader
- Uses Selenium to expand chapter groups and collect all links
- Uses cookies for login so content is accessible
"""

import cloudscraper
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import sys
import os
import re
import json

DELAY = 2.0
OUTPUT_FOLDER = "downloaded_novels"

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)


def slugify(text):
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "_", text)


def normalize_url(url):
    url = url.strip().rstrip("/")
    match = re.match(r"(https?://(?:www\.)?tomatomtl\.com/book/[^/]+)", url, re.I)
    if match:
        return match.group(1)
    return url


def load_cookies():
    raw = os.environ.get("TOMATO_COOKIES", "")
    if not raw:
        print("⚠️  No cookies — will get Login Required error!")
        return []
    try:
        cookies = json.loads(raw)
        # Also load into cloudscraper
        for c in cookies:
            scraper.cookies.set(c["name"], c["value"], domain=".tomatomtl.com")
        print(f"✅ Loaded {len(cookies)} cookies!")
        return cookies
    except Exception as e:
        print(f"⚠️  Cookie error: {e}")
        return []


def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36")
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def get_all_chapters(novel_url, cookies):
    """Use Selenium to expand all chapter groups and collect links."""
    print(f"\n🌐 Opening novel page in browser...")
    driver = get_driver()
    chapter_links = []
    title = "Unknown Novel"

    try:
        # Visit homepage first and inject cookies
        driver.get("https://tomatomtl.com")
        time.sleep(2)
        for c in cookies:
            try:
                driver.add_cookie({
                    "name": c["name"],
                    "value": c["value"],
                    "domain": ".tomatomtl.com"
                })
            except:
                pass

        # Go to novel page
        driver.get(novel_url)
        time.sleep(4)

        # Get title
        try:
            title = driver.find_element(By.TAG_NAME, "h1").text.strip()
            print(f"✅ Novel: {title}")
        except:
            print("⚠️  Could not get title")

        # Scroll down to chapter list section
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(2)

        # Find all chapter group buttons (e.g. "Chapter 1 - 50", "Chapter 51 - 100")
        # These are the collapsible accordion buttons
        wait = WebDriverWait(driver, 10)

        # Try to find and click all chapter group headers to expand them
        group_selectors = [
            "//div[contains(text(), 'Chapter') and contains(text(), '-')]",
            "//button[contains(text(), 'Chapter')]",
            "//*[contains(@class, 'chapter-group') or contains(@class, 'chapter-accordion')]",
            "//*[contains(@class, 'collapse') or contains(@class, 'accordion')]//button",
        ]

        groups_clicked = 0
        for selector in group_selectors:
            try:
                groups = driver.find_elements(By.XPATH, selector)
                if groups:
                    print(f"   Found {len(groups)} chapter groups with selector: {selector}")
                    for g in groups:
                        try:
                            driver.execute_script("arguments[0].click();", g)
                            time.sleep(0.5)
                            groups_clicked += 1
                        except:
                            pass
                    break
            except:
                pass

        print(f"   Clicked {groups_clicked} chapter group(s)")
        time.sleep(2)

        # Scroll through page to trigger any lazy loading
        for scroll in range(5):
            driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {(scroll+1)/5});")
            time.sleep(1)

        # Now collect all chapter links
        soup = BeautifulSoup(driver.page_source, "html.parser")
        seen = set()
        base = "https://tomatomtl.com"

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = base + href
            if re.search(r"/book/\d+/\d+", href, re.I) and href not in seen:
                seen.add(href)
                chapter_links.append({
                    "url": href,
                    "title": a.get_text(strip=True) or f"Chapter {len(chapter_links)+1}"
                })

        print(f"📚 Found {len(chapter_links)} chapters!")
        if chapter_links:
            print("   First 3:", [c["title"] for c in chapter_links[:3]])

    finally:
        driver.quit()

    return title, chapter_links


def fetch_chapter(url):
    """Download chapter content using cloudscraper (with cookies already loaded)."""
    resp = scraper.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Check for login wall
    if "login required" in resp.text.lower() or "log in to read" in resp.text.lower():
        return "[LOGIN REQUIRED — cookies may have expired, please refresh them]"

    # Content is in div class="tooi" (confirmed from previous debug)
    content_div = (
        soup.find("div", class_="tooi")
        or soup.find("div", class_=re.compile(r"tooi|chapter.?content|novel.?content", re.I))
        or soup.find("article")
        or soup.find("div", id=re.compile(r"content|chapter|reader", re.I))
    )

    if not content_div:
        divs = soup.find_all("div")
        if divs:
            content_div = max(divs, key=lambda d: len(d.get_text()))
        else:
            return "[Could not extract content]"

    for tag in content_div.find_all(["nav", "script", "style", "button", "aside", "header", "footer"]):
        tag.decompose()

    paragraphs = content_div.find_all("p")
    if paragraphs:
        return "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
    return content_div.get_text(separator="\n", strip=True)


def download_novel(raw_url, start_chapter=1, end_chapter=None):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    novel_url = normalize_url(raw_url)

    cookies = load_cookies()
    title, chapters = get_all_chapters(novel_url, cookies)

    if not chapters:
        print("❌ No chapters found!")
        sys.exit(1)

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

            try:
                content = fetch_chapter(ch["url"])
                f.write(content + "\n\n")
            except Exception as e:
                msg = f"[Error: {e}]"
                print(f"    ⚠️  {msg}")
                f.write(msg + "\n\n")

            time.sleep(DELAY)

    print(f"\n✅ Done! Saved to: {os.path.abspath(filename)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tomatomtl_downloader.py <url> [start] [end]")
        sys.exit(1)

    url = sys.argv[1]
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    end = int(sys.argv[3]) if len(sys.argv) > 3 else None

    download_novel(url, start, end)
