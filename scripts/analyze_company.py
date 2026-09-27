"""Step 1: analyze a company's website and save a CompanyProfile as JSON.

Run from the project root:
    python -m scripts.analyze_company https://example.com
    python -m scripts.analyze_company example.com --screenshot home.png
    python -m scripts.analyze_company example.com --screenshot latest   # newest screenshot
    python -m scripts.analyze_company example.com --web            # auto: Tavily if key, else OpenAI
    python -m scripts.analyze_company example.com --web tavily     # our search tool (works on Azure)
    python -m scripts.analyze_company example.com --web openai     # OpenAI built-in (not on Azure)
"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from agents.researcher import analyze_company
from core.web import normalize_url

parser = argparse.ArgumentParser(description="Build a company profile from its website.")
parser.add_argument("url", help="Company website, e.g. https://example.com")
parser.add_argument(
    "--screenshot",
    help="Path to a PNG/JPG screenshot of the homepage, or 'latest' for your newest screenshot",
)
parser.add_argument(
    "--web",
    nargs="?",
    const="auto",
    choices=["auto", "tavily", "openai"],
    help="Also search the web: tavily (any provider), openai (built-in, not Azure), auto (default)",
)
parser.add_argument(
    "--strict",
    action="store_true",
    help="Drop evidence quotes and competitors the grounding check cannot find in the sources",
)
args = parser.parse_args()

IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp"}


def latest_screenshot() -> Path | None:
    """Newest image in the usual Windows screenshot folders, or in this folder."""
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    folders = [
        home / "Pictures" / "Screenshots",
        home / "OneDrive" / "Pictures" / "Screenshots",
        Path.cwd(),
    ]
    images = [p for d in folders if d.is_dir() for p in d.iterdir() if p.suffix.lower() in IMAGE_TYPES]
    return max(images, key=lambda p: p.stat().st_mtime, default=None)


if args.screenshot == "latest":
    found = latest_screenshot()
    if found is None:
        print("No screenshot found in Pictures\\Screenshots or the project folder.")
        print("Take one with Win + PrtScn, then run again.")
        raise SystemExit(1)
    args.screenshot = str(found)
    print(f"Using screenshot: {found}")

# Fail early: check the screenshot before downloading the page or paying for a call.
if args.screenshot:
    shot = Path(args.screenshot)
    if not shot.is_file():
        print(f"Screenshot not found: {shot.resolve()}")
        print("Save the image in the project folder, or pass its full path, e.g.")
        print('  --screenshot "C:\\Users\\<you>\\Pictures\\Screenshots\\home.png"')
        images = sorted(p.name for p in Path.cwd().glob("*") if p.suffix.lower() in IMAGE_TYPES)
        if images:
            print("Images in this folder:", ", ".join(images))
        raise SystemExit(1)

url = normalize_url(args.url)
print(f"Analyzing {url} ...")
result = analyze_company(url, screenshot=args.screenshot, web=args.web, strict=args.strict)
profile, grounding = result.profile, result.grounding

out_dir = Path("data/output")
out_dir.mkdir(parents=True, exist_ok=True)
domain = urlparse(url).netloc.replace("www.", "") or "company"
out_file = out_dir / f"company_{domain}.json"
out_file.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
# The check goes in its own file, so step 2 reads a clean profile.
report_file = out_dir / f"company_{domain}.grounding.json"
report_file.write_text(json.dumps(grounding.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps(profile.model_dump(), ensure_ascii=False, indent=2))

if result.searches:
    print(f"\nSearches: {len(result.searches)}")
    for s_ in result.searches:
        print(f"  - {s_['query']}")

print("\nGrounding check")
found = sum(c.found for c in grounding.evidence)
print(f"  Evidence found on the website : {found}/{len(grounding.evidence)}")
for quote in grounding.unverified_evidence:
    print(f"    NOT FOUND: {quote}")
if not grounding.competitors_verifiable:
    print("  Competitors                   : cannot verify (built-in search gives no result text)")
elif grounding.competitors:
    found = sum(c.found for c in grounding.competitors)
    print(f"  Competitors found in sources  : {found}/{len(grounding.competitors)}")
    for c in grounding.competitors:
        mark = "ok " if c.found else "NOT FOUND"
        print(f"    {mark} {c.text}" + (f"  <- {c.where}" if c.where else ""))
if args.strict and not grounding.ok:
    print("  --strict: items NOT FOUND were removed from the saved profile.")

print(f"\nSaved to {out_file}")
print(f"Check saved to {report_file}")
print(f"Tokens (last call): {result.response.usage.input_tokens} in / {result.response.usage.output_tokens} out")
print("Every call, with its tokens, is in logs/calls.jsonl")
