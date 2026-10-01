"""Step 3: score fictional leads against the ICP, directly or through the Batch API.

Run from the project root, after steps 1 and 2:
    python -m scripts.make_leads                                   # once: 200 fictional leads
    python -m scripts.score_leads lucidya.com --mode direct --limit 20
    python -m scripts.score_leads lucidya.com --mode batch --dry-run   # write the JSONL only, free
    python -m scripts.score_leads lucidya.com --mode batch            # submit all leads
    python -m scripts.score_leads lucidya.com --check                 # status / download results
    python -m scripts.score_leads lucidya.com --check --wait          # poll until done
"""
import argparse
import collections
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import config
from agents.scorer import (TERMINAL, batch_model, load_icp, load_leads, read_batch_output, save_scores,
                           score_direct, submit_batch, write_batch_file)
from core.client import get_client
from core.cost import estimate_usd

OUT = Path("data/output")

parser = argparse.ArgumentParser(description="Score leads against the ICP.")
parser.add_argument("company", help="Domain used in steps 1-2, e.g. lucidya.com")
parser.add_argument("--leads", default="data/leads_sample.csv")
parser.add_argument("--mode", choices=["direct", "batch"], default="direct")
parser.add_argument("--limit", type=int, help="Score only the first N leads")
parser.add_argument("--workers", type=int, default=4, help="Parallel calls in direct mode")
parser.add_argument("--dry-run", action="store_true", help="Batch: write the JSONL file but do not submit")
parser.add_argument("--check", action="store_true", help="Check the last submitted batch")
parser.add_argument("--wait", action="store_true", help="With --check: poll every 30 s until done")
args = parser.parse_args()

domain = args.company.replace("www.", "")
state_file = OUT / f"batch_{domain}.json"
cache_key = f"icp-{domain}"


def summary(scores, usage, model, batch):
    counts = collections.Counter(s.recommendation for s in scores)
    print(f"\nScored {len(scores)} leads: "
          f"{counts['contact']} contact, {counts['nurture']} nurture, {counts['skip']} skip")
    by_segment = collections.Counter(s.segment for s in scores if s.recommendation != "skip")
    for segment, n in by_segment.most_common():
        print(f"  {n:3} worth pursuing in: {segment}")

    print("\nTop 5   (points: industry/region/size/signals)")
    for s in sorted(scores, key=lambda s: s.fit_score, reverse=True)[:5]:
        parts = f"{s.industry_points}/{s.region_points}/{s.size_points}/{s.signals_points}"
        print(f"  {s.fit_score:3}  {s.lead_id}  [{parts:>11}]  {s.segment}")
        for reason in s.reasons[:2]:
            print(f"                          - {reason}")
        if s.disqualifier:
            print(f"                          ! disqualifier: {s.disqualifier}")

    distinct = len({s.fit_score for s in scores})
    print(f"\nDistinct scores: {distinct} among {len(scores)} leads (more = finer ranking)")

    print(f"\nTokens: {usage.input_tokens} in ({usage.cached_tokens} cached = {usage.cache_share:.0%}) "
          f"/ {usage.output_tokens} out, {usage.requests} requests")
    cost = estimate_usd(usage, model, batch=batch)
    print(f"Estimated cost ({'batch' if batch else 'direct'}): ${cost:.4f}")
    if not batch:
        print(f"Same work through the Batch API:  ${estimate_usd(usage, model, batch=True):.4f}  (about half)")
    print("Prices are estimates; check your provider's pricing page.")


icp = load_icp(OUT / f"icp_{domain}.json")

# --- check a submitted batch ----------------------------------------------------
if args.check:
    if not state_file.is_file():
        raise SystemExit(f"No batch found for {domain}. Submit one first with --mode batch.")
    state = json.loads(state_file.read_text(encoding="utf-8"))
    client = get_client()
    while True:
        batch = client.batches.retrieve(state["batch_id"])
        c = batch.request_counts
        done = f"{c.completed}/{c.total} done, {c.failed} failed" if c else ""
        print(f"[{datetime.now():%H:%M:%S}] {batch.id}: {batch.status} {done}")
        if batch.status in TERMINAL or not args.wait:
            break
        time.sleep(30)

    if batch.status != "completed":
        if batch.status in TERMINAL:
            print("The batch did not complete.", batch.errors or "")
        else:
            print("Not finished yet. Run again later, or add --wait.")
        raise SystemExit(0)

    output = client.files.content(batch.output_file_id).text if batch.output_file_id else ""
    scores, usage, errors = read_batch_output(output)
    if batch.error_file_id:
        _, _, more = read_batch_output(client.files.content(batch.error_file_id).text)
        errors += more
    leads = load_leads(args.leads)
    path = save_scores(scores, leads, OUT / f"leads_scored_{domain}_batch.csv")
    summary(scores, usage, state["model"], batch=True)
    if errors:
        print(f"\n{len(errors)} requests failed, first: {errors[0]}")
    print(f"\nSaved to {path}")
    raise SystemExit(0)

leads = load_leads(args.leads, args.limit)
print(f"ICP segments: {', '.join(s.name for s in icp.segments)}")
print(f"Leads: {len(leads)} from {args.leads}")

# --- direct mode ------------------------------------------------------------------
if args.mode == "direct":
    model = config.model_for("fast")
    print(f"Mode: direct | model: {model} | {args.workers} in parallel")
    started = time.monotonic()
    scores, usage = score_direct(leads, icp, workers=args.workers, cache_key=cache_key)
    print(f"Done in {time.monotonic() - started:.0f} s")
    path = save_scores(scores, leads, OUT / f"leads_scored_{domain}_direct.csv")
    summary(scores, usage, model, batch=False)
    print(f"\nSaved to {path}")
    raise SystemExit(0)

# --- batch mode: write + submit -------------------------------------------------
model = batch_model()
jsonl = write_batch_file(leads, icp, OUT / f"batch_input_{domain}.jsonl", cache_key=cache_key)
size_kb = jsonl.stat().st_size / 1024
print(f"Mode: batch | model: {model} | wrote {len(leads)} requests to {jsonl} ({size_kb:.0f} KB)")
if args.dry_run:
    print("Dry run: nothing submitted. Open the file to see one request per line.")
    raise SystemExit(0)

batch = submit_batch(jsonl, description=f"mini-explee scoring {domain}")
state_file.write_text(json.dumps({
    "batch_id": batch.id, "model": model, "leads": len(leads),
    "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
}, indent=2), encoding="utf-8")
print(f"Submitted batch {batch.id} (status: {batch.status})")
print("It can take minutes to hours (max 24 h). Check with:")
print(f"  python -m scripts.score_leads {domain} --check")
