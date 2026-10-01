"""Tests for agents/writer.py and scripts/write_emails.py. No API, no network.

Run:  pytest -v
"""
import csv
import runpy
import sys
from types import SimpleNamespace

import numpy as np
import pytest

import config
from agents import writer
from core import client as core_client
from core import kb
from core.moderation import ModerationResult
from core.schemas import Claim, EmailDraft
from tests.test_icp import report as icp_report
from tests.test_kb import FakeEmbeddings
from tests.test_researcher import sample_profile

LEAD = {"lead_id": "L001", "company": "Zarnub Bank", "industry": "Banking", "country": "Saudi Arabia",
        "city": "Riyadh", "employees": "4200", "website": "zarnubbank.example",
        "description": "Zarnub Bank is a banking company.", "signals": "Active Arabic social media accounts"}

CHUNKS = [
    kb.Chunk("p1-c0", "https://acme.example/solutions/banking", "Banking",
             "Banks use Acme to track 95% of customer mentions in Arabic dialects in real time."),
    kb.Chunk("p2-c0", "https://acme.example/retail", "Retail", "Retail chains use Acme for reviews."),
]
SOURCES = [(CHUNKS[0], 0.91), (CHUNKS[1], 0.40)]

BODY = ("Hello Zarnub Bank team,\n\nBanks in Saudi Arabia hear from customers on many channels. "
        "Acme helps banks track 95% of customer mentions in Arabic dialects in real time, so teams "
        "can answer faster and spot issues early. Since you are active on Arabic social media, this "
        "could help your customer experience team see what people say about your services every "
        "day. Would a short 15-minute call next week be useful to see how this could work for you?")


def draft(body=BODY, claims=None, subject="Arabic customer insights for Zarnub Bank"):
    if claims is None:
        claims = [Claim(text="Acme helps banks track 95% of customer mentions", source_id="p1-c0",
                        quote="track 95% of customer mentions in Arabic dialects in real time")]
    return EmailDraft(subject=subject, body=body, claims=claims, personalization=["industry: Banking"])


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_FILE", str(tmp_path / "calls.jsonl"))


# --- checks ---------------------------------------------------------------------

def test_good_draft_passes_every_check():
    assert writer.check_draft(draft(), SOURCES, LEAD) == []


def test_claim_with_unknown_source_or_invented_quote_is_flagged():
    claims = [Claim(text="x", source_id="p9-c9", quote="anything"),
              Claim(text="y", source_id="p1-c0", quote="trusted by every bank in the world since 1990")]
    issues = writer.check_draft(draft(claims=claims), SOURCES, LEAD)
    assert any("unknown source 'p9-c9'" in i for i in issues)
    assert any("quote not found in p1-c0" in i for i in issues)


def test_numbers_must_come_from_sources_but_call_length_is_fine():
    body = BODY.replace("95%", "300%")
    issues = writer.check_draft(draft(body=body), SOURCES, LEAD)
    assert issues == ["number not found in sources: 300%"]  # "15-minute" is not flagged


def test_length_and_subject_rules():
    issues = writer.check_draft(draft(body="Hi. Short.", claims=[], subject="BUY NOW"), SOURCES, LEAD)
    assert any("words" in i for i in issues) and any("ALL CAPS" in i for i in issues)


def test_code_adds_signature_and_opt_out():
    text = writer.assemble(draft(), sample_profile())
    assert text.startswith("Subject: Arabic customer insights")
    assert "Best regards," in text and "Acme Logistics" in text
    assert text.endswith(writer.OPT_OUT)


# --- the request (caching + RAG) ---------------------------------------------------

def test_prefix_is_the_same_for_every_lead_and_sources_go_last():
    profile = sample_profile()
    assert writer.instructions_for(profile) == writer.instructions_for(profile)
    assert writer.instructions_for(profile).startswith(writer.RULES)
    text = writer.request_input(LEAD, icp_report().segments[0], SOURCES)
    assert text.index("LEAD:") < text.index("SOURCES:")
    assert "[p1-c0] (from https://acme.example/solutions/banking)" in text


def test_retrieval_query_uses_industry_and_segment():
    q = writer.retrieval_query(LEAD, icp_report().segments[0])
    assert "Banking" in q and "Saudi retail banks" in q


def test_load_contacts_keeps_only_contact_best_first(tmp_path):
    path = tmp_path / "scores.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["lead_id", "fit_score", "recommendation", "segment"])
        w.writerows([["L001", "75", "contact", "s"], ["L002", "95", "contact", "s"], ["L003", "50", "nurture", "s"]])
    leads = [dict(LEAD, lead_id=i) for i in ("L001", "L002", "L003")]
    pairs = writer.load_contacts(path, leads)
    assert [lead["lead_id"] for lead, _ in pairs] == ["L002", "L001"]


# --- one email end to end with fakes ----------------------------------------------

class FakeWriterClient(FakeEmbeddings):
    def __init__(self, drafts):
        super().__init__()
        self.drafts = list(drafts)
        self.parse_calls = []
        self.responses = SimpleNamespace(parse=self._parse)

    def _parse(self, **params):
        self.parse_calls.append(params)
        usage = SimpleNamespace(input_tokens=1500, output_tokens=300,
                                input_tokens_details=SimpleNamespace(cached_tokens=1024),
                                output_tokens_details=SimpleNamespace(reasoning_tokens=0))
        return SimpleNamespace(id="r", output=[], status="completed", output_parsed=self.drafts.pop(0), usage=usage)


def kb_with_chunks():
    fake = FakeEmbeddings()
    return kb.KnowledgeBase(CHUNKS, kb.embed([c.text for c in CHUNKS], client=fake))


def test_write_email_retrieves_writes_checks_moderates():
    fake = FakeWriterClient([draft()])
    clean = lambda text: ModerationResult(False, "test")
    email, _ = writer.write_email(LEAD, {"segment": "Saudi retail banks"}, sample_profile(), icp_report(),
                                  kb_with_chunks(), client=fake, moderate_fn=clean)

    assert email.status == "ready" and email.issues == []
    assert email.sources[0][0].id == "p1-c0"                      # banking passage retrieved first
    call = fake.parse_calls[0]
    assert call["text_format"] is EmailDraft and call["model"] == config.model_for("smart")
    assert "SOURCES:" in call["input"] and "p1-c0" in call["input"]


def test_flagged_moderation_sends_email_to_review():
    fake = FakeWriterClient([draft()])
    flagged = lambda text: ModerationResult(True, "test", ["harassment"])
    email, _ = writer.write_email(LEAD, {"segment": "Saudi retail banks"}, sample_profile(), icp_report(),
                                  kb_with_chunks(), client=fake, moderate_fn=flagged)
    assert email.status == "needs_review"
    assert any("moderation flagged" in i for i in email.issues)


# --- the script ---------------------------------------------------------------------

def test_script_writes_outbox_and_never_sends(tmp_path, monkeypatch):
    out = tmp_path / "data" / "output"
    out.mkdir(parents=True)
    (out / "company_acme.example.json").write_text(sample_profile().model_dump_json(), encoding="utf-8")
    (out / "icp_acme.example.json").write_text(icp_report().model_dump_json(), encoding="utf-8")
    with (out / "leads_scored_acme.example_direct.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["lead_id", "fit_score", "recommendation", "segment"])
        w.writerow(["L001", "90", "contact", "Saudi retail banks"])
    with (tmp_path / "data" / "leads_sample.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(LEAD))
        w.writeheader()
        w.writerow(LEAD)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(kb, "KB_DIR", tmp_path / "data" / "kb")
    fake = FakeWriterClient([draft()])
    kb.save("acme.example", CHUNKS, kb.embed([c.text for c in CHUNKS], client=fake))

    monkeypatch.setattr(config, "IS_AZURE", False)
    cats = SimpleNamespace(model_dump=lambda: {"harassment": False})
    fake.moderations = SimpleNamespace(create=lambda model, input: SimpleNamespace(
        results=[SimpleNamespace(flagged=False, categories=cats)]))
    monkeypatch.setattr(core_client, "_client", fake)
    monkeypatch.setattr(sys, "argv", ["write_emails", "acme.example", "--limit", "1"])
    runpy.run_module("scripts.write_emails", run_name="__main__")
    monkeypatch.setattr(core_client, "_client", None)

    txt = (out / "outbox" / "L001.txt").read_text(encoding="utf-8")
    assert txt.startswith(writer.SIMULATION_NOTE)
    assert "Status: ready" in txt and writer.OPT_OUT in txt and "[p1-c0]" in txt
    rows = list(csv.DictReader((out / "outbox" / "index.csv").open(encoding="utf-8-sig")))
    assert rows[0]["status"] == "ready"
