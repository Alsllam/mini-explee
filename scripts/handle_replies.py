"""Step 5: read the (fictional) replies, decide what to do, update the CRM.

Nothing is sent: reply drafts go to data/output/replies/ for a person to check.

Run from the project root, after steps 1-4:
    python -m scripts.make_replies                 # once: 12 fictional replies
    python -m scripts.handle_replies lucidya.com
    python -m scripts.handle_replies lucidya.com --limit 3
"""
import argparse
import time
from pathlib import Path

import config
from pipeline.icp import load_profile
from pipeline.replies import (
    ReplyContext,
    build_agents,
    configure_tracing,
    handle_reply,
    load_replies,
    log_run,
    save_replies,
    sdk_model,
    update_crm,
    update_do_not_contact,
)
from pipeline.scorer import load_leads
from core.cost import Usage, estimate_usd
from core.kb import KnowledgeBase

OUT = Path("data/output")

parser = argparse.ArgumentParser(description="Handle replies with the OpenAI Agents SDK (never sends anything).")
parser.add_argument("company", help="Domain used in steps 1-4, e.g. lucidya.com")
parser.add_argument("--replies", default="data/replies_sample.jsonl")
parser.add_argument("--leads", default="data/leads_sample.csv")
parser.add_argument("--limit", type=int, help="Handle only the first N replies")
args = parser.parse_args()

domain = args.company.replace("www.", "")
profile = load_profile(OUT / f"company_{domain}.json")
leads = {lead["lead_id"]: lead for lead in load_leads(args.leads)}
replies = load_replies(args.replies, args.limit)
try:
    kb = KnowledgeBase.load(domain)
except FileNotFoundError:
    kb = None
    print("No knowledge base: product questions will go to a human. Build it with scripts.build_kb.")

tracing = configure_tracing()
triage = build_agents(profile, sdk_model)
print(f"Sender: {profile.name} | {len(replies)} replies | triage: {config.model_for('fast')}"
      f" | specialists: {config.model_for('smart')} | tracing: {'on' if tracing else 'off'}\n")

handled, usage = [], Usage()
started = time.monotonic()
for reply in replies:
    ctx = ReplyContext(reply=reply, leads=leads, profile=profile, kb=kb, outbox=OUT / "outbox")
    h = handle_reply(reply, triage, ctx)
    handled.append(h)
    log_run(h)
    if h.usage:
        usage.input_tokens += h.usage["input_tokens"]
        usage.cached_tokens += h.usage["cached_tokens"]
        usage.output_tokens += h.usage["output_tokens"]
        usage.requests += h.usage["requests"]

    match = "" if not reply.expected else ("  =" if h.decision.category == reply.expected
                                           else f"  (expected {reply.expected})")
    print(f"{reply.reply_id} {reply.company[:22]:22} {h.decision.category:15}{match}")
    print(f"     {' -> '.join(h.path)} | tools: {', '.join(h.tools) or 'none'} | "
          f"{h.decision.next_action}{' ' + h.decision.follow_up_date if h.decision.follow_up_date else ''}"
          f" | CRM: {h.status}")
    for issue in h.issues:
        print(f"     ! {issue}")

save_replies(handled, OUT / "replies", profile)
update_crm(handled, OUT / "crm.csv")
dnc = update_do_not_contact(handled, OUT / "do_not_contact.csv")

agree = sum(h.decision.category == h.reply.expected for h in handled if h.reply.expected)
with_expected = sum(1 for h in handled if h.reply.expected)
guarded = sum(h.guardrail == "opt-out" for h in handled)
print(f"\nCategory matches expected: {agree}/{with_expected} | opt-outs caught by code: {guarded} (no model call)")
print(f"Needs a human: {sum(h.status == 'needs_human' for h in handled)} | {time.monotonic() - started:.0f} s")
if usage.requests:
    print(f"Tokens: {usage.input_tokens} in ({usage.cache_share:.0%} cached) / {usage.output_tokens} out, "
          f"{usage.requests} model calls, ~${estimate_usd(usage, config.model_for('smart')):.4f}")
print(f"Saved: {OUT / 'replies'}/, {OUT / 'crm.csv'}, {dnc}. Nothing was sent.")
