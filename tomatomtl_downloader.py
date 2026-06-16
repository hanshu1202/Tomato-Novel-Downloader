#!/usr/bin/env python3
"""
Tomato MTL Novel Chapter Downloader
Just paste any TomatoMTL URL - novel page OR chapter page - it handles both!
"""

import requests
from bs4 import BeautifulSoup
import time
import sys
import os
import re

DELAY = 1.5
OUTPUT_FOLDER = "downloaded_novels"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.tomatomtl.com/",
}

session = requests.Session()
session.headers.update(HEADERS)


def slugify(text):
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "_", text)


def normalize_url(url):
    """Accept any TomatoMTL URL - novel page or chapter page - and return the novel index URL."""
    url = url.strip().rstrip("/")
    # If user pasted a chapter URL, strip back to the novel page
    match = re.match(r"(https?://(?:www\.)?tomatomtl\.com/novel/[^/]+)", url, re.I)
    if match:
        return match.group(1)
    return url


def get_novel_info(novel_url):
    print(f"\n📖 Fetching novel page: {novel_url}")
    resp = session.get(novel_url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Title
    title_tag = soup.find("h1") 
    title = title_tag.get_text(strip=True) if title_tag else "Unknown Novel"
    print(f"✅ Novel: {title}")

    # Chapter links
    chapter_links = []
    seen = set()
    base = "https://www.tomatomtl.com"

    # Try all anchor tags that look like chapters
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            href = base + href
        # Chapter URLs typically contain /chapter/ or /ch-
        if re.search(r"/chapter|/ch-\d", href, re.I) and href not in seen:
            seen.add(href)
            chapter_links.append({"url": href, "title": a.get_text(strip=True) or f"Chapter {len(chapter_links)+1}"})

    print(f"📚 Found {len(chapter_links)} chapters")
    return {"title": title, "chapters": chapter_links}


def fetch_chapter(url):
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    content_div = (
        soup.find("div", class_=re.compile(r"chapter.?content|novel.?content|read.?content", re.I))
        or soup.find("article")
        or soup.find("div", id=re.compile(r"content|chapter", re.I))
    )

    if not content_div:
        return "[Could not extract chapter content]"

    for tag in content_div.find_all(["nav", "script", "style", "button", "aside"]):
        tag.decompose()

    paragraphs = content_div.find_all("p")
    if paragraphs:
        return "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
    return content_div.get_text(separator="\n", strip=True)


def download_novel(raw_url):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    novel_url = normalize_url(raw_url)

    info = get_novel_info(novel_url)
    title = info["title"]
    chapters = info["chapters"]

    if not chapters:
        print("❌ No chapters found. Please make sure the URL is correct.")
        sys.exit(1)

    filename = os.path.join(OUTPUT_FOLDER, f"{slugify(title)}.txt")
    print(f"\n💾 Saving to: {filename}")
    print("─" * 50)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"{title}\n{'=' * len(title)}\nSource: {novel_url}\n\n\n")

        for i, ch in enumerate(chapters, 1):
            ch_title = ch["title"] or f"Chapter {i}"
            print(f"  [{i}/{len(chapters)}] {ch_title}")

            f.write(f"\n{'─'*60}\n{ch_title}\n{'─'*60}\n\n")

            try:
                content = fetch_chapter(ch["url"])
                f.write(content + "\n\n")
            except Exception as e:
                msg = f"[Error: {e}]"
                print(f"    ⚠️  {msg}")
                f.write(msg + "\n\n")

            time.sleep(DELAY)

    print(f"\n✅ Done! {len(chapters)} chapters saved to: {os.path.abspath(filename)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tomatomtl_downloader.py <url>")
        sys.exit(1)
    download_novel(sys.argv[1])
