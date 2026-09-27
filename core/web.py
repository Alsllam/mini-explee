"""Fetch a web page and turn it into clean text for the model.

Why not send the raw HTML? Most of a page's HTML is scripts, styles and
markup. The model would pay for all those tokens (lesson 1.2) and still have
to dig for the few sentences that matter. We strip it down first.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# About 4 characters per token for English, fewer for Arabic. 12,000 characters
# keeps one page at roughly 3,000-6,000 input tokens: plenty for a homepage.
MAX_CHARS = 12_000

HEADERS = {
    # Some sites refuse requests that don't look like a browser.
    "User-Agent": "Mozilla/5.0 (compatible; mini-explee/0.1; learning project)",
    "Accept-Language": "ar,en;q=0.8",
}


@dataclass
class Page:
    url: str
    title: str = ""
    description: str = ""
    headings: list[str] = field(default_factory=list)
    text: str = ""
    truncated: bool = False

    def as_prompt(self) -> str:
        """The page as one block of text, labelled so the model knows each part."""
        parts = [f"URL: {self.url}"]
        if self.title:
            parts.append(f"TITLE: {self.title}")
        if self.description:
            parts.append(f"META DESCRIPTION: {self.description}")
        if self.headings:
            parts.append("HEADINGS:\n- " + "\n- ".join(self.headings))
        parts.append("PAGE TEXT:\n" + self.text)
        if self.truncated:
            parts.append(f"(text cut at {MAX_CHARS} characters)")
        return "\n\n".join(parts)


def normalize_url(url: str) -> str:
    """Add https:// when the user typed just 'example.com'."""
    url = url.strip()
    if not urlparse(url).scheme:
        url = "https://" + url
    return url


def parse_html(html: str, url: str, max_chars: int = MAX_CHARS) -> Page:
    """Extract title, description, headings and visible text from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove parts a visitor never reads.
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "template"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    description = (meta.get("content") or "").strip() if meta else ""

    headings = []
    for h in soup.find_all(["h1", "h2", "h3"]):
        words = h.get_text(" ", strip=True)
        if words and words not in headings:
            headings.append(words)

    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    truncated = len(text) > max_chars

    return Page(
        url=url,
        title=title,
        description=description,
        headings=headings[:25],
        text=text[:max_chars],
        truncated=truncated,
    )


def fetch_page(url: str, timeout: float = 15.0) -> Page:
    """Download a page and parse it. Raises requests.HTTPError on 4xx/5xx."""
    url = normalize_url(url)
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding  # Arabic pages
    return parse_html(resp.text, url)
