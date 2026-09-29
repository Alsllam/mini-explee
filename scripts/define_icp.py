"""Step 2: propose ideal customer segments, then refine them in a conversation.

Run from the project root, after step 1 saved a profile:
    python -m scripts.define_icp lucidya.com
    python -m scripts.define_icp data/output/company_lucidya.com.json
    python -m scripts.define_icp lucidya.com --feedback "Focus on banks" --feedback "Add Egypt"

Without --feedback it asks you for feedback after each version; press Enter
on an empty line to finish.
"""
import argparse
import json
from pathlib import Path

import config
from agents.icp import load_profile, propose_icp, refine_icp
from core.schemas import ICPReport

OUT_DIR = Path("data/output")

parser = argparse.ArgumentParser(description="Define ideal customer segments for a company.")
parser.add_argument("company", help="Domain analyzed in step 1 (lucidya.com) or the JSON file path")
parser.add_argument("--feedback", action="append", default=[], help="Feedback turn (repeatable)")
parser.add_argument("--effort", choices=["minimal", "low", "medium", "high"],
                    help="Override REASONING_EFFORT for this run")
args = parser.parse_args()

if args.effort:
    config.REASONING_EFFORT = args.effort

source = Path(args.company)
if source.suffix != ".json":
    source = OUT_DIR / f"company_{args.company.replace('www.', '')}.json"
domain = source.stem.removeprefix("company_")


def show(report: ICPReport, version: int, response) -> None:
    print(f"\n=== Version {version}: {report.change_summary}")
    for i, seg in enumerate(report.segments, 1):
        print(f"\n[{i}] {seg.name}  (priority: {seg.priority})")
        print(f"    {seg.description}")
        print(f"    Size: {seg.company_size} | Regions: {', '.join(seg.regions)}")
        print(f"    Buyers: {', '.join(seg.buyer_roles)}")
        print("    Why fit:")
        for reason in seg.why_fit:
            print(f"      - {reason}")
    if report.assumptions:
        print("\nAssumptions:")
        for a in report.assumptions:
            print(f"  - {a}")
    if report.questions_for_user:
        print("\nQuestions for you:")
        for q in report.questions_for_user:
            print(f"  - {q}")

    usage = response.usage
    details = getattr(usage, "output_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", 0) or 0
    print(f"\nTokens: {usage.input_tokens} in / {usage.output_tokens} out "
          f"(of which {reasoning} reasoning) | response id: {response.id}")


def save(report: ICPReport, version: int) -> Path:
    path = OUT_DIR / f"icp_{domain}_v{version}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


profile = load_profile(source)
print(f"Profile: {profile.name} ({source})")
print(f"Model: {config.model_for('reasoning')} | reasoning effort: {config.REASONING_EFFORT or 'off'}")
print("Thinking... (reasoning models can take 20-60 seconds)")

report, response = propose_icp(profile)
version = 1
show(report, version, response)
save(report, version)

pending = list(args.feedback)
interactive = not pending
while True:
    if pending:
        feedback = pending.pop(0)
        print(f"\n> {feedback}")
    elif interactive:
        feedback = input("\nYour feedback (Enter to finish): ").strip()
    else:
        break
    if not feedback:
        break
    report, response = refine_icp(feedback, response.id)
    version += 1
    show(report, version, response)
    save(report, version)

final = OUT_DIR / f"icp_{domain}.json"
final.write_text(report.model_dump_json(indent=2), encoding="utf-8")
print(f"\nFinal ICP (version {version}) saved to {final}")
print(f"All versions: {OUT_DIR}/icp_{domain}_v1..v{version}.json")
