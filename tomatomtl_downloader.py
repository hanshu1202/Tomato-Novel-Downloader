#!/usr/bin/env python3
"""
Tomato MTL Novel Chapter Downloader - with login support
"""

import cloudscraper
from bs4 import BeautifulSoup
import time
import sys
import os
import re

DELAY = 2.0
OUTPUT_FOLDER = "downloaded_novels"

scraper = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "windows",
        "mobile": False
    }
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


def login(email, password):
    """Login to TomatoMTL to unlock all chapters."""
    if not email or not password:
        print("⚠️  No login credentials provided — downloading as guest (max 5 chapters)")
        return False

    print(f"\n🔐 Logging in as {email} ...")

    # Visit homepage first
    scraper.get("https://tomatomtl.com", timeout=15)
    time.sleep(2)

    # Find login page
    login_url = "https://tomatomtl.com/login"
    resp = scraper.get(login_url, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")

    # Get CSRF token if present
    csrf = None
    csrf_tag = soup.find("input", {"name": re.compile(r"csrf|token|_token", re.I)})
    if csrf_tag:
        csrf = csrf_tag.get("value")

    # Submit login form
    payload = {
        "email": email,
        "password": password,
    }
    if csrf:
        payload["_token"] = csrf

    # Try to find the actual form action URL
    form = soup.find("form")
    action = login_url
    if form and form.get("action"):
        action = form["action"]
        if not action.startswith("http"):
            action = "https://tomatomtl.com" + action

    resp = scraper.post(action, data=payload, timeout=15)
    time.sleep(2)

    # Check if login worked
    if "logout" in resp.text.lower() or "profile" in resp.text.lower() or resp.url == "https://tomatomtl.com/":
        print("✅ Login successful!")
        return True
    else:
        print("⚠️  Login may have failed — check your email/password in GitHub Secrets")
        print("   Continuing anyway...")
        return False


def get_novel_info(novel_url):
    print(f"\n📖 Fetching novel page: {novel_url}")

    resp = scraper.get(novel_url, timeout=15)
    print(f"   Status: {resp.status_code}")
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Unknown Novel"
    print(f"✅ Novel: {title}")

    chapter_links = []
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

    print(f"📚 Found {len(chapter_links)} chapters total")
    return {"title": title, "chapters": chapter_links}


def fetch_chapter(url):
    resp = scraper.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    content_div = (
        soup.find("div", class_=re.compile(r"chapter.?content|novel.?content|read.?content|content.?area", re.I))
        or soup.find("article")
        or soup.find("div", id=re.compile(r"content|chapter", re.I))
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

    info = get_novel_info(novel_url)
    title = info["title"]
    chapters = info["chapters"]

    if not chapters:
        print("❌ No chapters found. Please check the URL.")
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
                content = fetch_chapter(ch["url"])
                f.write(content + "\n\n")
            except Exception as e:
                msg = f"[Error fetching this chapter: {e}]"
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

    # Get login credentials from environment variables (GitHub Secrets)
    email = os.environ.get("TOMATO_EMAIL", "")
    password = os.environ.get("TOMATO_PASSWORD", "")

    login(email, password)
    download_novel(url, start, end)
