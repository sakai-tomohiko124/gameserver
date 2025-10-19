"""scraper.py
Simple scraper to fetch novel metadata (title, author, description, cover) from a public novel page.

Important: this module fetches only metadata (title, author, brief description/summary) and
does NOT scrape or store the full copyrighted novel text. Use responsibly and respect the
target site's robots.txt and terms of service.
"""
from typing import Dict, Optional
import requests
from bs4 import BeautifulSoup


def fetch_novel_metadata(url: str, timeout: float = 10.0) -> Optional[Dict[str, str]]:
    """Fetch metadata from the given novel URL.

    Returns a dict with keys: title, author, description, cover (may be None) or None on failure.
    """
    try:
        headers = {"User-Agent": "gameserver/1.0 (+https://example.com)"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Title: try common selectors used on alphapolis pages
        title_tag = soup.find("h1") or soup.find(class_=lambda c: c and "title" in c)
        title = title_tag.get_text(strip=True) if title_tag else None

        # Author: look for element that contains '作者' or a byline
        author = None
        author_sel = soup.find(lambda tag: tag.name in ["a", "span", "p"] and "作者" in tag.get_text())
        if author_sel:
            author = author_sel.get_text(strip=True).replace("作者:", "").strip()
        else:
            # fallback: pick an element with class containing 'author' or a link near title
            a = soup.find(class_=lambda c: c and "author" in c.lower())
            if a:
                author = a.get_text(strip=True)

        # Description: many pages have a synopsis box; try common selectors
        desc = None
        desc_sel = soup.find(class_=lambda c: c and ("description" in c.lower() or "synopsis" in c.lower() or "あらすじ" in c))
        if desc_sel:
            desc = desc_sel.get_text(strip=True)
        else:
            # try meta description tag
            meta = soup.find("meta", attrs={"name": "description"})
            if meta and meta.get('content'):
                desc = meta['content'].strip()

        # Cover image
        cover = None
        og = soup.find("meta", property="og:image")
        if og and og.get('content'):
            cover = og['content']

        data = {
            "title": title or "",
            "author": author or "",
            "description": desc or "",
            "cover": cover or "",
        }
        return data
    except Exception:
        return None
