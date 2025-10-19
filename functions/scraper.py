"""scraper.py
Simple scraper to fetch novel metadata (title, author, description, cover) from a public novel page.

Important: this module fetches only metadata (title, author, brief description/summary) and
does NOT scrape or store the full copyrighted novel text. Use responsibly and respect the
target site's robots.txt and terms of service.
"""
from typing import Dict, Optional
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup


def fetch_novel_metadata(url: str, timeout: float = 10.0, session: Optional[requests.Session] = None) -> Optional[Dict[str, str]]:
    """Fetch metadata from the given novel URL.

    Improvements over the simple implementation:
    - Uses a requests.Session with a Retry adapter (on network/server errors and 429)
    - Uses a more realistic User-Agent to avoid basic bot-blocking
    - Adds logging for easier debugging of failures
    - Accepts an optional session for testing/mockability

    Returns a dict with keys: title, author, description, cover (may be empty string) or None on failure.
    """
    # Configure session with retries if caller did not supply one
    created_session = False
    if session is None:
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(['GET', 'HEAD']))
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        created_session = True

    headers = {
        # Use a common browser UA string to reduce chance of being blocked
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    }

    try:
        resp = session.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.exception('Failed to fetch URL %s: %s', url, e)
        # only close session if we created it here
        if created_session:
            try:
                session.close()
            except Exception:
                pass
        return None

    try:
        soup = BeautifulSoup(resp.text, "html.parser")

        # Title: try several selectors including common meta tags
        title = None
        # Prefer og:title or meta title
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content'].strip()
        if not title:
            title_tag = soup.find('h1') or soup.find(class_=lambda c: c and 'title' in c.lower())
            if title_tag:
                title = title_tag.get_text(strip=True)

        # Author
        author = None
        # try meta author
        meta_author = soup.find('meta', attrs={'name': 'author'})
        if meta_author and meta_author.get('content'):
            author = meta_author['content'].strip()
        if not author:
            author_sel = soup.find(lambda tag: tag.name in ['a', 'span', 'p'] and '作者' in (tag.get_text() or ''))
            if author_sel:
                author = author_sel.get_text(strip=True).replace('作者:', '').strip()
            else:
                a = soup.find(class_=lambda c: c and 'author' in c.lower())
                if a:
                    author = a.get_text(strip=True)

        # Description
        desc = None
        desc_sel = soup.find(class_=lambda c: c and ('description' in c.lower() or 'synopsis' in c.lower() or 'あらすじ' in c))
        if desc_sel:
            desc = desc_sel.get_text(strip=True)
        else:
            meta = soup.find('meta', attrs={'name': 'description'})
            if meta and meta.get('content'):
                desc = meta['content'].strip()

        # Cover image
        cover = None
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            cover = og['content']

        data = {
            'title': title or '',
            'author': author or '',
            'description': desc or '',
            'cover': cover or '',
        }

        return data
    except Exception as e:
        logging.exception('Failed to parse HTML for %s: %s', url, e)
        return None
