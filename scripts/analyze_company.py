"""Step 1: analyze a company's website and save a CompanyProfile as JSON.

Run from the project root:
    python -m scripts.analyze_company https://example.com
    python -m scripts.analyze_company example.com --screenshot home.png
    python -m scripts.analyze_company example.com --screenshot latest   # newest screenshot
    python -m scripts.analyze_company example.com --web      # OpenAI only
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
parser.add_argument("--web", action="store_true", help="Also use the web_search tool (OpenAI only)")
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
profile, response = analyze_company(url, screenshot=args.screenshot, use_web_search=args.web)

out_dir = Path("data/output")
out_dir.mkdir(parents=True, exist_ok=True)
domain = urlparse(url).netloc.replace("www.", "") or "company"
out_file = out_dir / f"company_{domain}.json"
out_file.write_text(profile.model_dump_json(indent=2), encoding="utf-8")

print(json.dumps(profile.model_dump(), ensure_ascii=False, indent=2))
print(f"\nSaved to {out_file}")
print(f"Tokens: {response.usage.input_tokens} in / {response.usage.output_tokens} out")
