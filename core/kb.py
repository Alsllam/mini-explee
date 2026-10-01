"""A small knowledge base for RAG: crawl a site, chunk it, embed it, search it.

RAG = Retrieval-Augmented Generation:
  1. Retrieval    - find the few passages most related to the question
  2. Augmentation - put those passages into the prompt
  3. Generation   - the model answers from them, not from memory

Pipeline (scripts/build_kb.py runs steps 1-4 once; the writer runs step 5 per email):
  1. crawl()        a few pages of the company's own website
  2. chunk_page()   split each page into overlapping passages of ~800 characters
  3. embed()        turn every passage into a vector (a list of numbers) whose
                    direction captures its meaning
  4. save()         passages -> chunks.jsonl, vectors -> vectors.npy
  5. search()       embed the query, compare with every vector (cosine
                    similarity), return the closest passages

No vector database: a few hundred vectors fit in memory and numpy compares
them all in a millisecond. A real database (Azure AI Search, pgvector...)
matters at hundreds of thousands of passages.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import numpy as np
import requests
from bs4 import BeautifulSoup

import config
from core.client import get_client
from core.web import HEADERS, Page, fetch_page, normalize_url, parse_html

KB_DIR = Path("data/kb")

# Pages whose links contain these words are crawled first: they usually hold
# what a sales email needs (solutions per industry, products, proof).
PRIORITY_WORDS = ["solution", "industr", "bank", "financ", "retail", "government", "telecom",
                  "hospitality", "case", "customer", "success", "product", "platform", "about"]
SKIP_WORDS = ["login", "signin", "signup", "register", "careers", "jobs", "privacy", "terms",
              "cookie", "blog/page", "tag/", "author/", ".pdf", ".jpg", ".png", "mailto:", "tel:"]

CHUNK_CHARS = 800
CHUNK_OVERLAP = 150
EMBED_BATCH = 64


@dataclass
class Chunk:
    id: str
    url: str
    title: str
    text: str


# --- 1. crawl -----------------------------------------------------------------

def pick_links(html: str, base_url: str, limit: int) -> list[str]:
    """Same-site links, most useful first (PRIORITY_WORDS), junk removed."""
    site = urlparse(base_url).netloc
    seen, scored = set(), []
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        url = urljoin(base_url, a["href"]).split("#")[0].rstrip("/")
        low = url.lower()
        if urlparse(url).netloc != site or url in seen or url == base_url.rstrip("/"):
            continue
        if any(w in low for w in SKIP_WORDS):
            continue
        seen.add(url)
        score = sum(w in low for w in PRIORITY_WORDS)
        scored.append((-score, len(url), url))  # best score first, then shorter URLs
    return [url for *_, url in sorted(scored)[:limit]]


def robots_allows(url: str, fetch=requests.get) -> bool:
    """Respect robots.txt: the site's own rules for automated visitors."""
    parts = urlparse(url)
    rp = robotparser.RobotFileParser()
    try:
        resp = fetch(f"{parts.scheme}://{parts.netloc}/robots.txt", headers=HEADERS, timeout=10)
        rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
    except requests.RequestException:
        rp.parse([])  # no robots.txt reachable -> nothing forbidden
    return rp.can_fetch(HEADERS["User-Agent"], url)


def crawl(start_url: str, max_pages: int = 8, delay: float = 1.0, fetch=None, get=requests.get) -> list[Page]:
    """The start page + up to max_pages-1 linked pages from the same site.

    Polite by design: checks robots.txt, waits `delay` seconds between pages.
    """
    start_url = normalize_url(start_url)
    fetch = fetch or fetch_page
    if not robots_allows(start_url, get):
        raise PermissionError(f"robots.txt of {urlparse(start_url).netloc} does not allow crawling {start_url}")

    resp = get(start_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = getattr(resp, "apparent_encoding", None) or resp.encoding
    pages = [parse_html(resp.text, start_url)]  # reuse this download for page 1
    for url in pick_links(resp.text, start_url, max_pages - 1):
        if not robots_allows(url, get):
            continue
        time.sleep(delay)
        try:
            pages.append(fetch(url))
            print(f"[crawl] {url}")
        except requests.RequestException as err:
            print(f"[crawl] skipped {url}: {type(err).__name__}")
    return pages


# --- 2. chunk -------------------------------------------------------------------

def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split into ~size-character pieces that end at a word boundary.

    The overlap repeats the end of one piece at the start of the next, so a
    sentence cut in half still appears whole in one of the two pieces.
    """
    text = " ".join(text.split())
    pieces, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            space = text.rfind(" ", start + size // 2, end)
            end = space if space > start else end
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in pieces if len(p) > 40]


def chunk_page(page: Page, page_no: int) -> list[Chunk]:
    # Headings and description first: they summarise the page in few words.
    head = " ".join([page.title, page.description, *page.headings[:8]])
    return [Chunk(f"p{page_no}-c{i}", page.url, page.title, piece)
            for i, piece in enumerate(chunk_text(head + " " + page.text))]


# --- 3. embed -------------------------------------------------------------------

def embed(texts: list[str], client=None) -> np.ndarray:
    """One vector per text, normalized to length 1 (so a dot product = cosine)."""
    client = client or get_client()
    model = config.checked_name("MODEL_EMBED", config.MODEL_EMBED)
    vectors = []
    for i in range(0, len(texts), EMBED_BATCH):  # many texts per request: fewer calls
        resp = client.embeddings.create(model=model, input=texts[i:i + EMBED_BATCH])
        vectors.extend(item.embedding for item in resp.data)
    matrix = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1, norms)


# --- 4. save / load -------------------------------------------------------------

def kb_dir(domain: str) -> Path:
    return KB_DIR / domain.replace("www.", "")


def save(domain: str, chunks: list[Chunk], vectors: np.ndarray) -> Path:
    folder = kb_dir(domain)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    np.save(folder / "vectors.npy", vectors)
    (folder / "meta.json").write_text(json.dumps(
        {"model": config.MODEL_EMBED, "chunks": len(chunks), "dims": int(vectors.shape[1])}, indent=2),
        encoding="utf-8")
    return folder


@dataclass
class KnowledgeBase:
    chunks: list[Chunk]
    vectors: np.ndarray

    @classmethod
    def load(cls, domain: str) -> "KnowledgeBase":
        folder = kb_dir(domain)
        if not (folder / "vectors.npy").is_file():
            raise FileNotFoundError(f"No knowledge base in {folder}. Build it: python -m scripts.build_kb {domain}")
        lines = (folder / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        return cls([Chunk(**json.loads(line)) for line in lines], np.load(folder / "vectors.npy"))

    # --- 5. search ----------------------------------------------------------------
    def search(self, query: str, k: int = 3, client=None, query_vector: np.ndarray | None = None) -> list[tuple[Chunk, float]]:
        """The k passages closest in meaning to the query, with their similarity (-1..1)."""
        q = query_vector if query_vector is not None else embed([query], client=client)[0]
        scores = self.vectors @ q  # cosine similarity with every passage at once
        best = np.argsort(-scores)[:k]
        return [(self.chunks[i], float(scores[i])) for i in best]
