"""Step 4: write a checked email draft for every lead scored "contact" in step 3.

Nothing is sent: drafts go to data/output/outbox/ as text files.

Run from the project root, after steps 1-3 and build_kb:
    python -m scripts.write_emails lucidya.com --limit 3
    python -m scripts.write_emails lucidya.com --scores data/output/leads_scored_lucidya.com_batch.csv
"""
import argparse
import time
from pathlib import Path

import config
from agents.icp import load_profile
from agents.scorer import load_icp, load_leads
from agents.writer import load_contacts, save_outbox, write_email
from core.cost import Usage, estimate_usd
from core.kb import KnowledgeBase

OUT = Path("data/output")

parser = argparse.ArgumentParser(description="Write email drafts with RAG + checks (never sent).")
parser.add_argument("company", help="Domain used in steps 1-3, e.g. lucidya.com")
parser.add_argument("--scores", help="Scored leads CSV (default: the direct-mode file from step 3)")
parser.add_argument("--leads", default="data/leads_sample.csv")
parser.add_argument("--limit", type=int, default=3, help="How many emails to write (best leads first)")
args = parser.parse_args()

domain = args.company.replace("www.", "")
scores = Path(args.scores) if args.scores else OUT / f"leads_scored_{domain}_direct.csv"
if not scores.is_file():
    raise SystemExit(f"{scores} not found. Run step 3 first: python -m scripts.score_leads {domain}")

profile = load_profile(OUT / f"company_{domain}.json")
icp = load_icp(OUT / f"icp_{domain}.json")
kb = KnowledgeBase.load(domain)
contacts = load_contacts(scores, load_leads(args.leads), args.limit)
print(f"Sender: {profile.name} | knowledge base: {len(kb.chunks)} passages | writing {len(contacts)} emails")
print(f"Model: {config.model_for('smart')} | embeddings: {config.MODEL_EMBED}\n")

emails, usage = [], Usage()
started = time.monotonic()
for lead, row in contacts:
    email, response = write_email(lead, row, profile, icp, kb)
    u = response.usage
    usage.add(u.input_tokens, getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0), u.output_tokens)
    emails.append(email)

    mark = "OK " if email.status == "ready" else "!! "
    print(f"{mark} {email.lead_id}  {email.company}  ({row['segment']}, score {row['fit_score']})")
    print(f"     Subject: {email.subject}")
    print(f"     Sources: {', '.join(f'{c.id} ({s:.2f})' for c, s in email.sources)}"
          f" | claims: {len(email.draft.claims)} | moderation: {'flagged' if email.moderation.flagged else 'clean'}")
    for issue in email.issues:
        print(f"     ! {issue}")

folder = save_outbox(emails, OUT / "outbox")
ready = sum(e.status == "ready" for e in emails)
print(f"\n{ready}/{len(emails)} ready, {len(emails) - ready} need review | {time.monotonic() - started:.0f} s")
print(f"Tokens: {usage.input_tokens} in ({usage.cache_share:.0%} cached) / {usage.output_tokens} out")
print(f"Estimated cost: ${estimate_usd(usage, config.model_for('smart')):.4f} (writing only; embeddings and moderation extra)")
print(f"Drafts saved to {folder} - open the .txt files to review. Nothing was sent.")
