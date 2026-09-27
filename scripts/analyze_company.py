"""Step 1: analyze a company's website and save a CompanyProfile as JSON.

Run from the project root:
    python -m scripts.analyze_company https://example.com
    python -m scripts.analyze_company example.com --screenshot home.png
    python -m scripts.analyze_company example.com --web      # OpenAI only
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from agents.researcher import analyze_company
from core.web import normalize_url

parser = argparse.ArgumentParser(description="Build a company profile from its website.")
parser.add_argument("url", help="Company website, e.g. https://example.com")
parser.add_argument("--screenshot", help="Path to a PNG/JPG screenshot of the homepage")
parser.add_argument("--web", action="store_true", help="Also use the web_search tool (OpenAI only)")
args = parser.parse_args()

# Fail early: check the screenshot before downloading the page or paying for a call.
if args.screenshot:
    shot = Path(args.screenshot)
    if not shot.is_file():
        print(f"Screenshot not found: {shot.resolve()}")
        print("Save the image in the project folder, or pass its full path, e.g.")
        print('  --screenshot "C:\\Users\\<you>\\Pictures\\Screenshots\\home.png"')
        images = sorted(p.name for p in Path.cwd().glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
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
