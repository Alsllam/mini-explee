"""Agent 3 - the lead scorer.

Input : the final ICP from step 2 + a CSV of leads (fictional companies)
Output: a LeadScore per lead (core/schemas.py)

The same request is sent two ways, so we can compare them fairly:
  direct : one normal API call per lead, answers in seconds
  batch  : all requests in one JSONL file through the Batch API (lesson 4.4),
           about half the price, answers within 24 hours

Course lessons used here:
  2.1 Model choice      - task="fast": a small cheap model for a simple, repeated task
  2.4 Prompt caching    - the long ICP sits at the START of every request, identical
                          each time, so the provider can reuse it (cached_tokens)
  2.5 Structured Outputs- a strict JSON schema, written by hand into the request
                          because a batch file can't carry a Pydantic class.
                          The model returns points per criterion; code adds them.
  4.4 Batch API         - upload JSONL, create a batch, poll, download results
"""
from __future__ import annotations

import csv
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai.lib._pydantic import to_strict_json_schema

import config
from core.client import ask, get_client
from core.cost import Usage
from core.schemas import ICPReport, LeadAssessment, LeadScore

RUBRIC = """You assess sales leads for the company whose ideal customer profile (ICP)
is given below. For each lead, pick the ONE best-matching segment, then judge
each criterion separately. Give points per criterion only: do NOT add them up,
the total is computed by code.

Criteria and maximum points:
- industry_points  (0-35): the lead's industry vs the segment's industries.
  35 = listed exactly, about 20 = closely related, 0 = unrelated.
- region_points    (0-25): the lead's country vs the segment's regions.
  25 = listed, about 10 = same wider region (e.g. GCC), 0 = outside.
- size_points      (0-20): the lead's employees vs the segment's company_size.
  20 = inside the range, about 10 = near it, 0 = far from it.
- signals_points   (0-20): the lead's signals vs the segment's signals.
  About 7 per matching signal, up to 20. 0 if the lead lists no signals.
- disqualifier: quote a segment disqualifier that the lead's fields show,
  otherwise an empty string.
If no segment fits at all, segment = "none".

Rules:
- Use ONLY the lead fields given. Do not assume facts about the company.
- Use the whole range: different leads should rarely get identical points.

IDEAL CUSTOMER PROFILE:
"""

# Temperature 0: the same lead should get the same score every run.
# Leave SCORING_TEMPERATURE empty in .env if MODEL_FAST is a reasoning model.
_temp = os.getenv("SCORING_TEMPERATURE", "0").strip()
SCORING_TEMPERATURE = float(_temp) if _temp else None


# --- inputs ------------------------------------------------------------------

def load_icp(path: str | Path) -> ICPReport:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found. Run step 2 first: python -m scripts.define_icp <domain>")
    return ICPReport.model_validate_json(path.read_text(encoding="utf-8"))


def load_leads(path: str | Path, limit: int | None = None) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        leads = list(csv.DictReader(f))
    return leads[:limit] if limit else leads


def lead_text(lead: dict) -> str:
    """One lead as labelled lines. Only this part changes between requests."""
    fields = ["lead_id", "company", "industry", "country", "city", "employees", "description", "signals"]
    return "LEAD:\n" + "\n".join(f"{k}: {lead.get(k, '')}" for k in fields)


# --- the request (shared by direct and batch) ---------------------------------

def instructions_for(icp: ICPReport) -> str:
    """Rubric + ICP: long and IDENTICAL for every lead -> cacheable prefix (lesson 2.4)."""
    return RUBRIC + icp.model_dump_json(indent=1)


def text_format() -> dict:
    """Structured Outputs as plain JSON, usable in a batch file (no Python objects)."""
    return {
        "format": {
            "type": "json_schema",
            "name": "LeadAssessment",
            "schema": to_strict_json_schema(LeadAssessment),
            "strict": True,
        }
    }


def build_request(lead: dict, icp: ICPReport, model: str, cache_key: str | None = None) -> dict:
    """The Responses API body for one lead. Order matters for caching:
    instructions (same every time) first, the lead (different every time) last."""
    body = {
        "model": model,
        "instructions": instructions_for(icp),
        "input": lead_text(lead),
        "text": text_format(),
    }
    if SCORING_TEMPERATURE is not None:
        body["temperature"] = SCORING_TEMPERATURE
    # prompt_cache_key groups requests that share a prefix on the same cache
    # machine (OpenAI). Not sent to Azure, where caching works automatically.
    if cache_key and not config.IS_AZURE:
        body["prompt_cache_key"] = cache_key
    return body


# Maximum points per criterion, and the caps applied by code.
MAX_POINTS = {"industry_points": 35, "region_points": 25, "size_points": 20, "signals_points": 20}
DISQUALIFIED_CAP = 20   # a disqualifier applies -> at most 20
NO_SEGMENT_CAP = 19     # no segment fits -> below 20


def to_score(a: LeadAssessment, lead_id: str) -> LeadScore:
    """The arithmetic, done by code: clamp each criterion, add, apply the caps.

    The model judges; the code counts. The same assessment always gives the
    same score, and the recommendation can never contradict the score.
    """
    points = {name: max(0, min(top, getattr(a, name))) for name, top in MAX_POINTS.items()}
    total = sum(points.values())
    disqualifier = a.disqualifier.strip()
    if disqualifier:
        total = min(total, DISQUALIFIED_CAP)
    segment = a.segment.strip() or "none"
    if segment.lower() == "none":
        total = min(total, NO_SEGMENT_CAP)
    recommendation = "contact" if total >= 70 else "nurture" if total >= 40 else "skip"
    return LeadScore(
        lead_id=lead_id,  # trust our id, not the model's copy of it
        segment=segment,
        fit_score=total,
        disqualifier=disqualifier,
        reasons=a.reasons,
        missing_info=a.missing_info,
        recommendation=recommendation,
        **points,
    )


def parse_score(text: str, lead_id: str) -> LeadScore:
    return to_score(LeadAssessment.model_validate_json(text), lead_id)


# --- direct mode ---------------------------------------------------------------

def score_direct(leads: list[dict], icp: ICPReport, *, workers: int = 4, cache_key: str | None = None,
                 client=None) -> tuple[list[LeadScore], Usage]:
    """One normal call per lead, a few in parallel. Returns scores in lead order."""
    model = config.model_for("fast")
    usage = Usage()
    lock = threading.Lock()  # several threads update the same counters

    def one(lead: dict) -> LeadScore:
        body = build_request(lead, icp, model, cache_key)
        body.pop("model")  # ask() picks the model from task="fast"
        response = ask(task="fast", client=client, **body)
        u = response.usage
        details = getattr(u, "input_tokens_details", None)
        with lock:
            usage.add(u.input_tokens, getattr(details, "cached_tokens", 0), u.output_tokens)
        return parse_score(response.output_text, lead["lead_id"])

    if not leads:
        return [], usage
    # Cache warm-up (lesson 2.4): the FIRST request runs alone. It fills the
    # cache with the shared prefix, so every parallel request after it can
    # reuse it. Started all at once, the first few would all miss the cache.
    first = one(leads[0])
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rest = list(pool.map(one, leads[1:]))
    return [first, *rest], usage


# --- batch mode (lesson 4.4) ---------------------------------------------------

def batch_model() -> str:
    if config.IS_AZURE and not config.MODEL_BATCH:
        raise ValueError(
            "On Azure the Batch API needs a 'Global Batch' deployment. Create one in Azure AI "
            "Foundry and set MODEL_BATCH=<its deployment name> in .env "
            "(see docs/step-03-lead-scoring.md)."
        )
    if config.MODEL_BATCH:
        return config.checked_name("MODEL_BATCH", config.MODEL_BATCH)
    return config.model_for("fast")


def write_batch_file(leads: list[dict], icp: ICPReport, path: str | Path, cache_key: str | None = None) -> Path:
    """One JSON line per lead: custom_id + method + url + body."""
    model = batch_model()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for lead in leads:
            line = {
                "custom_id": lead["lead_id"],  # how we match each answer to its lead
                "method": "POST",
                "url": "/v1/responses",
                "body": build_request(lead, icp, model, cache_key),
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return path


def submit_batch(jsonl_path: str | Path, *, client=None, description: str = "mini-explee lead scoring"):
    """Upload the file, then create the batch. Returns the Batch object."""
    client = client or get_client()
    with Path(jsonl_path).open("rb") as f:
        uploaded = client.files.create(file=f, purpose="batch")
    return client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/responses",
        completion_window="24h",
        metadata={"description": description},
    )


TERMINAL = {"completed", "failed", "expired", "cancelled"}


def read_batch_output(text: str) -> tuple[list[LeadScore], Usage, list[dict]]:
    """Parse the output JSONL: one line per request, in ANY order (match by custom_id)."""
    scores, errors, usage = [], [], Usage()
    for raw in text.splitlines():
        if not raw.strip():
            continue
        line = json.loads(raw)
        lead_id = line.get("custom_id", "?")
        response = line.get("response") or {}
        body = response.get("body") or {}
        if line.get("error") or response.get("status_code") != 200:
            errors.append({"lead_id": lead_id, "error": line.get("error") or body.get("error")})
            continue
        u = body.get("usage") or {}
        usage.add(u.get("input_tokens", 0),
                  (u.get("input_tokens_details") or {}).get("cached_tokens", 0),
                  u.get("output_tokens", 0))
        scores.append(parse_score(_output_text(body), lead_id))
    return scores, usage, errors


def _output_text(body: dict) -> str:
    """The raw JSON response has no .output_text helper: collect the text parts."""
    return "".join(
        part.get("text", "")
        for item in body.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )


# --- output --------------------------------------------------------------------

def save_scores(scores: list[LeadScore], leads: list[dict], path: str | Path) -> Path:
    """CSV sorted best first, with the company name next to each score."""
    by_id = {lead["lead_id"]: lead for lead in leads}
    rows = sorted(scores, key=lambda s: s.fit_score, reverse=True)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # -sig: Excel shows Arabic correctly
        writer = csv.writer(f)
        writer.writerow(["lead_id", "company", "industry", "country", "employees",
                         "fit_score", "recommendation", "segment",
                         "industry_pts", "region_pts", "size_pts", "signals_pts", "disqualifier",
                         "reasons", "missing_info"])
        for s in rows:
            lead = by_id.get(s.lead_id, {})
            writer.writerow([s.lead_id, lead.get("company", ""), lead.get("industry", ""),
                             lead.get("country", ""), lead.get("employees", ""), s.fit_score,
                             s.recommendation, s.segment,
                             s.industry_points, s.region_points, s.size_points, s.signals_points,
                             s.disqualifier, " | ".join(s.reasons), " | ".join(s.missing_info)])
    return path
