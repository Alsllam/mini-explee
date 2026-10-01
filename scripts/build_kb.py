"""Step 4a: build the knowledge base (RAG) from the company's own website.

Run from the project root:
    python -m scripts.build_kb lucidya.com
    python -m scripts.build_kb lucidya.com --start https://lucidya.com --max-pages 10
    python -m scripts.build_kb lucidya.com --dry-run      # crawl + chunk only, no embeddings

Emails are in English, so start from the English version of the site if there
is one. Embeddings also match across languages, but less precisely.
"""
import argparse
import time

import config
from core.kb import chunk_page, crawl, embed, save

parser = argparse.ArgumentParser(description="Crawl a website and build a searchable knowledge base.")
parser.add_argument("company", help="Domain used in earlier steps, e.g. lucidya.com (the KB folder name)")
parser.add_argument("--start", help="Start URL (default: https://<company>)")
parser.add_argument("--max-pages", type=int, default=8)
parser.add_argument("--dry-run", action="store_true", help="Crawl and chunk, but do not call the embeddings API")
args = parser.parse_args()

domain = args.company.replace("www.", "")
start = args.start or f"https://{domain}"
print(f"Crawling {start} (up to {args.max_pages} pages, 1 s apart, robots.txt respected)")

pages = crawl(start, max_pages=args.max_pages)
chunks = [c for n, page in enumerate(pages) for c in chunk_page(page, n)]
chars = sum(len(c.text) for c in chunks)
print(f"\n{len(pages)} pages -> {len(chunks)} chunks ({chars:,} characters, ~{chars // 4:,} tokens)")
for page in pages:
    print(f"  - {page.title[:70] or page.url}")

if args.dry_run:
    print("\nDry run: no embeddings created. Example chunk:\n")
    print(chunks[0].text[:500] if chunks else "(none)")
    raise SystemExit(0)

print(f"\nEmbedding with {config.MODEL_EMBED} ...")
started = time.monotonic()
vectors = embed([c.text for c in chunks])
folder = save(domain, chunks, vectors)
print(f"Done in {time.monotonic() - started:.1f} s: {vectors.shape[0]} vectors x {vectors.shape[1]} numbers")

# Embeddings are cheap: about $0.02 per million tokens for text-embedding-3-small
# (approximate list price; check your pricing page). ~4 characters per token.
EMBED_PRICE_PER_M = 0.02
print(f"Estimated cost: ${chars / 4 * EMBED_PRICE_PER_M / 1e6:.5f}")
print(f"Saved to {folder}")
