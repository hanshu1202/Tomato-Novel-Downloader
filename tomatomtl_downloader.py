#!/usr/bin/env python3
"""
Tomato MTL Novel Chapter Downloader - with debug mode to fix chapter detection
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

    # DEBUG: print all links
    print("\n🔍 DEBUG — All links on page:")
    all_links = soup.find_all("a", href=True)
    print(f"   Total links: {len(all_links)}")
    for a in all_links[:50]:
        print(f"   HREF: {repr(a['href'])}  TEXT: {repr(a.get_text(strip=True)[:40])}")

    # DEBUG: print all div classes
    print("\n🔍 DEBUG — Div classes:")
    for d in soup.find_all("div", class_=True)[:20]:
        print(f"   {d.get('class')}")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Unknown Novel"
    print(f"\n✅ Novel title: {title}")

    chapter_links = []
    seen = set()
    base = "https://tomatomtl.com"

    for a in all_links:
        href = a["href"]
        if not href.startswith("http"):
            href = base + href
        if (
            re.search(r"/book/\d+/\d+", href, re.I) or
            re.search(r"/chapter/\d+", href, re.I) or
            re.search(r"/read/", href, re.I) or
            re.search(r"/ch-\d+", href, re.I)
        ) and href not in seen:
            seen.add(href)
            chapter_links.append({
                "url": href,
                "title": a.get_text(strip=True) or f"Chapter {len(chapter_links)+1}"
            })

    print(f"📚 Found {len(chapter_links)} chapters")
    return {"title": title, "chapters": chapter_links}


def fetch_chapter(url, debug=False):
    resp = scraper.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    if debug:
        print(f"\n🔍 DEBUG chapter page div classes:")
        for d in soup.find_all("div", class_=True)[:15]:
            print(f"   {d.get('class')}")

    content_div = (
        soup.find("div", class_=re.compile(r"chapter.?content|novel.?content|read.?content|content.?area|article.?content|passage|reader", re.I))
        or soup.find("article")
        or soup.find("div", id=re.compile(r"content|chapter|reader|text", re.I))
        or soup.find("section", class_=re.compile(r"content|chapter|read", re.I))
    )

    if not content_div:
        divs = soup.find_all("div")
        if divs:
            content_div = max(divs, key=lambda d: len(d.get_text()))
        else:
            return "[Could not extract chapter content]"

    for tag in content_div.find_all(["nav", "script", "style", "button", "aside", "header", "footer"]):
        tag.decompose()

    paragraphs = content_div.find_all("p")
    if paragraphs:
        return "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
    return content_div.get_text(separator="\n", strip=True)


def download_novel(raw_url, start_chapter=1, end_chapter=None):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    novel_url = normalize_url(raw_url)

    load_cookies()
    info = get_novel_info(novel_url)
    title = info["title"]
    chapters = info["chapters"]

    if not chapters:
        print("❌ No chapters found — check DEBUG output above!")
        sys.exit(1)

    total = len(chapters)
    start = max(1, start_chapter) - 1
    end = min(end_chapter, total) if end_chapter else total
    selected = chapters[start:end]

    print(f"\n📌 Downloading chapters {start+1} to {end} (out of {total} total)")

    safe_title = slugify(title)
    filename = os.path.join(OUTPUT_FOLDER, f"{safe_title}_ch{start+1}_to_{end}.txt")
    print(f"💾 Saving to: {filename}\n{'─'*50}")

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"{title}\n{'='*len(title)}\n")
        f.write(f"Chapters: {start+1} to {end}\n")
        f.write(f"Source: {novel_url}\n\n\n")

        for i, ch in enumerate(selected, start+1):
            ch_title = ch["title"] or f"Chapter {i}"
            print(f"  [{i}/{end}] {ch_title}")

            f.write(f"\n{'─'*60}\n{ch_title}\n{'─'*60}\n\n")

            try:
                # Only show debug info on first chapter
                content = fetch_chapter(ch["url"], debug=(i == start+1))
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
