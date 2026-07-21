#!/usr/bin/env python3
"""
Tomato MTL Novel Chapter Downloader
- Handles JS-loaded chapter lists via API
- Uses correct selectors for chapter content extraction
"""

import cloudscraper
from bs4 import BeautifulSoup
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


def get_book_id(url):
    match = re.search(r"/book/(\d+)", url)
    return match.group(1) if match else None


def load_cookies():
    raw = os.environ.get("TOMATO_COOKIES", "")
    if not raw:
        print("⚠️  No cookies found — downloading as guest")
        return
    try:
        cookies = json.loads(raw)
        for c in cookies:
            scraper.cookies.set(c["name"], c["value"], domain=".tomatomtl.com")
        print(f"✅ Loaded {len(cookies)} cookies — logged in!")
    except Exception as e:
        print(f"⚠️  Could not load cookies: {e}")


def get_novel_info(novel_url):
    print(f"\n📖 Fetching novel page: {novel_url}")

    try:
        scraper.get("https://tomatomtl.com", timeout=15)
        time.sleep(2)
    except:
        pass

    resp = scraper.get(novel_url, timeout=15)
    print(f"   Status: {resp.status_code}")
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Get title
    title_tag = soup.find("h1") or soup.find("h2")
    title = title_tag.get_text(strip=True) if title_tag else "Unknown Novel"

    # If title still empty, try meta tag
    if not title or title.strip() == "":
        meta = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "title"})
        if meta:
            title = meta.get("content", "Unknown Novel")

    print(f"✅ Novel title: {title}")

    book_id = get_book_id(novel_url)
    print(f"📘 Book ID: {book_id}")

    # Try TomatoMTL's API to get full chapter list
    chapter_links = []
    
    # Method 1: Try their chapter list API
    api_urls = [
        f"https://tomatomtl.com/book/{book_id}/chapters",
        f"https://tomatomtl.com/api/book/{book_id}/chapters",
        f"https://tomatomtl.com/api/chapters?book_id={book_id}",
    ]

    for api_url in api_urls:
        try:
            print(f"   Trying API: {api_url}")
            r = scraper.get(api_url, timeout=15)
            if r.status_code == 200:
                print(f"   API response: {r.text[:300]}")
                try:
                    data = r.json()
                    print(f"   JSON keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                    break
                except:
                    pass
        except Exception as e:
            print(f"   API failed: {e}")

    # Method 2: Use the one chapter link we found + increment through chapters
    # We found: /book/7528360449612467262/7651523370248307225
    # Try to find all chapter links including paginated ones
    base = "https://tomatomtl.com"
    seen = set()

    # Get all chapter links from page
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

    # Method 3: Try fetching paginated chapter list pages
    for page in range(1, 20):
        page_url = f"{novel_url}?page={page}"
        try:
            r = scraper.get(page_url, timeout=15)
            if r.status_code != 200:
                break
            psoup = BeautifulSoup(r.text, "html.parser")
            found_new = False
            for a in psoup.find_all("a", href=True):
                href = a["href"]
                if not href.startswith("http"):
                    href = base + href
                if re.search(r"/book/\d+/\d+", href, re.I) and href not in seen:
                    seen.add(href)
                    chapter_links.append({
                        "url": href,
                        "title": a.get_text(strip=True) or f"Chapter {len(chapter_links)+1}"
                    })
                    found_new = True
            if not found_new:
                break
            time.sleep(1)
        except:
            break

    print(f"📚 Found {len(chapter_links)} chapters total")
    return {"title": title, "chapters": chapter_links}


def fetch_chapter(url):
    resp = scraper.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the chapter content container using the correct ID
    content_div = soup.find("article", id="chapter_content") or soup.find("div", id="chapter_content")

    if not content_div:
        # Fallback to finding the largest text container
        divs = soup.find_all("div")
        if divs:
            content_div = max(divs, key=lambda d: len(d.get_text()))
        else:
            return "[Could not extract chapter content]"

    # Remove unwanted elements
    for tag in content_div.find_all(["nav", "script", "style", "button", "aside", "header", "footer"]):
        tag.decompose()

    # Extract text from span.kxa (translation spans) first
    paragraphs = []
    for span in content_div.find_all("span", class_="kxa"):
        # Prefer translation (English) over original text
        text = span.get("transtext") or span.get("orgtext") or span.get_text(strip=True)
        if text and text.strip():
            paragraphs.append(text.strip())

    # If no span.kxa found, try regular paragraphs
    if not paragraphs:
        paragraphs = content_div.find_all("p")
        if paragraphs:
            return "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

    # Join collected text with proper spacing
    if paragraphs:
        return "\n\n".join(paragraphs)

    # Final fallback: get all text from container
    return content_div.get_text(separator="\n", strip=True)


def download_novel(raw_url, start_chapter=1, end_chapter=None):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    novel_url = normalize_url(raw_url)

    load_cookies()
    info = get_novel_info(novel_url)
    title = info["title"] or "novel"
    chapters = info["chapters"]

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
