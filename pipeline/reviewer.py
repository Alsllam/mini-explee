"""Agent 4.1 - the reviewer: a second model that judges each email draft.

Why a second model? Step 4's checks are plain code. They catch INVENTION
(an unknown source, a fake quote, a made-up number) but not EXAGGERATION:
  - a real quote that does not prove the claim attached to it
    ("Hotels need CX platforms" used to claim "we help you respond faster")
  - a claim that adds a word the quote does not have ("AI-powered")
  - a promise about the sender that the writer never listed as a claim
Spotting those needs understanding, so we ask a model. But the model only
JUDGES; code decides what each verdict means and sets the status
(same principle as step 3b: the model judges, the code counts).

Course lessons used here:
  2.5 Structured Outputs - EmailReview, one verdict per claim
Plus a concept beyond the numbered lessons: evaluation with an
"LLM as a judge", using a fixed rubric.
"""
from __future__ import annotations

import os

from core.client import ask
from core.grounding import normalize
from core.kb import Chunk
from core.schemas import EmailDraft, EmailReview

_temp = os.getenv("REVIEW_TEMPERATURE", "0").strip()
REVIEW_TEMPERATURE = float(_temp) if _temp else None  # a judge should be repeatable

JUDGE = """You are a strict fact-checker for B2B sales emails. You do not rewrite
anything; you only judge.

You receive the EMAIL BODY, its numbered CLAIMS (each with the id of a SOURCE
passage and a quote copied from it), the SOURCE passages, and the LEAD SIGNALS.

1. For every claim, decide whether its quote proves it. Judge the meaning, not
   the language: a quote in Arabic can prove a claim in English. Be strict:
   if the claim says more than the quote, it is "partial"; if the quote is
   about something else (a market need, a different product), "unsupported".
2. Find sentences in the body that say what the SENDER does, can do, has done
   or promises, and that no listed claim covers.
3. List which lead signals the body refers to.
"""


def review_input(draft: EmailDraft, sources: list[tuple[Chunk, float]], lead: dict) -> str:
    claims = "\n".join(f"{i}. {c.text}\n   source: {c.source_id}\n   quote: \"{c.quote}\""
                       for i, c in enumerate(draft.claims, 1)) or "(none)"
    passages = "\n\n".join(f"[{c.id}]\n{c.text}" for c, _ in sources)
    signals = "\n".join(f"- {s}" for s in lead_signals(lead)) or "(none)"
    return (f"EMAIL BODY:\n{draft.body}\n\nCLAIMS:\n{claims}\n\n"
            f"SOURCES:\n{passages}\n\nLEAD SIGNALS:\n{signals}")


def lead_signals(lead: dict) -> list[str]:
    return [s.strip() for s in (lead.get("signals") or "").split(";") if s.strip()]


def review_email(draft: EmailDraft, sources, lead: dict, *, client=None):
    """Returns (EmailReview, response). Uses the FAST model: judging is a simpler
    task than writing, and a different model is less likely to share the
    writer's blind spots."""
    extra = {} if REVIEW_TEMPERATURE is None else {"temperature": REVIEW_TEMPERATURE}
    response = ask(review_input(draft, sources, lead), task="fast", instructions=JUDGE,
                   text_format=EmailReview, client=client, **extra)
    review = response.output_parsed
    if review is None:
        raise RuntimeError(f"No review for {lead.get('lead_id')}. Status: {getattr(response, 'status', '?')}")
    return review, response


def review_issues(review: EmailReview, draft: EmailDraft, lead: dict) -> list[str]:
    """Code decides what the verdicts mean. Empty list = the judge found nothing."""
    issues = []
    by_no = {v.claim_no: v for v in review.claims}
    for i, claim in enumerate(draft.claims, 1):
        v = by_no.get(i)
        if v is None:
            issues.append(f"reviewer gave no verdict for claim {i} [{claim.source_id}]")
        elif v.verdict == "unsupported":
            issues.append(f"claim {i} not supported by its quote [{claim.source_id}]: {v.reason}")
        elif v.verdict == "partial":
            issues.append(f"claim {i} says more than its quote [{claim.source_id}]: {v.reason}")

    for sentence in review.unlisted_claims:
        issues.append(f"unlisted claim about the sender: {sentence}")

    # Trust only signals that really are in the lead's data (the judge can slip too).
    known = {normalize(s): s for s in lead_signals(lead)}
    used = [known[normalize(s)] for s in review.signals_used if normalize(s) in known]
    if known and not used:
        issues.append("no lead signal used; strongest candidates: " + "; ".join(known.values()))
    return issues
