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
from core.schemas import Claim, ClaimVerdict, EmailDraft, EmailReview
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


def test_empty_sender_name_falls_back_to_team(monkeypatch):
    # .env.example ships "SENDER_NAME=" (empty): the signature must not lose the name.
    monkeypatch.setenv("SENDER_NAME", "")
    text = writer.assemble(draft(), sample_profile())
    assert "Best regards,\nThe Acme Logistics team\nAcme Logistics" in text
    monkeypatch.setenv("SENDER_NAME", "Sara Ahmed")
    assert "Best regards,\nSara Ahmed\n" in writer.assemble(draft(), sample_profile())


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

def clean_review(n_claims=1, signals=("Active Arabic social media accounts",)):
    return EmailReview(claims=[ClaimVerdict(claim_no=i, verdict="supported", reason="the quote says it")
                               for i in range(1, n_claims + 1)],
                       unlisted_claims=[], signals_used=list(signals))


def _usage():
    return SimpleNamespace(input_tokens=1500, output_tokens=300,
                           input_tokens_details=SimpleNamespace(cached_tokens=1024),
                           output_tokens_details=SimpleNamespace(reasoning_tokens=0))


class FakeWriterClient(FakeEmbeddings):
    """parse() answers the writer from `drafts` and the reviewer from `reviews`
    (a clean review when none is queued); create() answers query translation."""

    def __init__(self, drafts, reviews=()):
        super().__init__()
        self.drafts = list(drafts)
        self.reviews = list(reviews)
        self.parse_calls, self.create_calls = [], []
        self.responses = SimpleNamespace(parse=self._parse, create=self._create_text)

    def _parse(self, **params):
        self.parse_calls.append(params)
        if params["text_format"] is EmailReview:
            parsed = self.reviews.pop(0) if self.reviews else clean_review()
        else:
            parsed = self.drafts.pop(0)
        return SimpleNamespace(id="r", output=[], status="completed", output_parsed=parsed, usage=_usage())

    def _create_text(self, **params):
        self.create_calls.append(params)
        return SimpleNamespace(id="t", output=[], status="completed", output_text="بنوك تجربة العملاء",
                               usage=_usage())

    def writer_calls(self):
        return [c for c in self.parse_calls if c["text_format"] is EmailDraft]


def kb_with_chunks():
    fake = FakeEmbeddings()
    return kb.KnowledgeBase(CHUNKS, kb.embed([c.text for c in CHUNKS], client=fake))


def test_write_email_retrieves_writes_checks_moderates():
    fake = FakeWriterClient([draft()])
    clean = lambda text: ModerationResult(False, "test")
    email, _ = writer.write_email(LEAD, {"segment": "Saudi retail banks"}, sample_profile(), icp_report(),
                                  kb_with_chunks(), client=fake, moderate_fn=clean)

    assert email.status == "ready" and email.issues == [] and email.revisions == 0
    assert email.sources[0][0].id == "p1-c0"                      # banking passage retrieved first
    call = fake.writer_calls()[0]
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
    assert "Review (second model):" in txt and "claim 1: supported" in txt
    assert "Status: ready" in txt and writer.OPT_OUT in txt and "[p1-c0]" in txt
    rows = list(csv.DictReader((out / "outbox" / "index.csv").open(encoding="utf-8-sig")))
    assert rows[0]["status"] == "ready"


# --- step 4.1: the reviewer -----------------------------------------------------------

from agents import reviewer  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_query_cache():
    writer._QUERY_CACHE.clear()
    yield
    writer._QUERY_CACHE.clear()


def two_claims():
    return [Claim(text="Acme helps banks track 95% of customer mentions", source_id="p1-c0",
                  quote="track 95% of customer mentions in Arabic dialects in real time"),
            Claim(text="Acme's AI answers every review for retail chains", source_id="p2-c0",
                  quote="Retail chains use Acme for reviews")]


def test_review_input_numbers_claims_and_lists_signals():
    text = reviewer.review_input(draft(claims=two_claims()), SOURCES, LEAD)
    assert "1. Acme helps banks" in text and "2. Acme's AI answers" in text
    assert "source: p2-c0" in text and "[p1-c0]" in text
    assert text.endswith("- Active Arabic social media accounts")


def test_code_turns_verdicts_into_issues():
    review = EmailReview(
        claims=[ClaimVerdict(claim_no=1, verdict="supported", reason="ok"),
                ClaimVerdict(claim_no=2, verdict="partial", reason="'AI answers every review' is not in the quote")],
        unlisted_claims=["We can help you streamline this process."],
        signals_used=["Active Arabic social media accounts"])
    issues = reviewer.review_issues(review, draft(claims=two_claims()), LEAD)
    assert issues == [
        "claim 2 says more than its quote [p2-c0]: 'AI answers every review' is not in the quote",
        "unlisted claim about the sender: We can help you streamline this process.",
    ]


def test_missing_verdict_unsupported_claim_and_unused_signals_are_issues():
    review = EmailReview(claims=[ClaimVerdict(claim_no=1, verdict="unsupported", reason="a market need")],
                         unlisted_claims=[], signals_used=[])
    issues = reviewer.review_issues(review, draft(claims=two_claims()), LEAD)
    assert issues[0].startswith("claim 1 not supported by its quote [p1-c0]")
    assert issues[1] == "reviewer gave no verdict for claim 2 [p2-c0]"
    assert issues[2].startswith("no lead signal used")


def test_a_signal_the_judge_invented_does_not_count():
    review = clean_review(signals=["Opened 40 new branches"])     # not in the lead's data
    issues = reviewer.review_issues(review, draft(), LEAD)
    assert issues == ["no lead signal used; strongest candidates: Active Arabic social media accounts"]


def test_reviewer_uses_fast_model_and_temperature_zero():
    fake = FakeWriterClient([], reviews=[clean_review()])
    review, _ = reviewer.review_email(draft(), SOURCES, LEAD, client=fake)
    call = fake.parse_calls[0]
    assert call["model"] == config.model_for("fast") and call["temperature"] == 0
    assert call["instructions"] == reviewer.JUDGE and review.claims[0].verdict == "supported"


def write(fake, **kw):
    clean = lambda text: ModerationResult(False, "test")
    return writer.write_email(LEAD, {"segment": "Saudi retail banks"}, sample_profile(), icp_report(),
                              kb_with_chunks(), client=fake, moderate_fn=clean, **kw)


def test_review_problems_send_the_draft_back_once_then_it_is_ready():
    bad = EmailReview(claims=[ClaimVerdict(claim_no=1, verdict="partial", reason="adds 'AI-powered'")],
                      unlisted_claims=[], signals_used=["Active Arabic social media accounts"])
    fake = FakeWriterClient([draft(), draft()], reviews=[bad, clean_review()])
    email, usage = write(fake)

    assert email.status == "ready" and email.revisions == 1
    assert email.first_issues == ["claim 1 says more than its quote [p1-c0]: adds 'AI-powered'"]
    second = fake.writer_calls()[1]["input"]
    assert "REVIEW OF YOUR PREVIOUS DRAFT" in second and "adds 'AI-powered'" in second
    assert usage["smart"].requests == 2                     # two drafts
    assert usage["fast"].requests == 3                      # translation + two reviews


def test_still_wrong_after_one_revision_goes_to_review():
    bad = EmailReview(claims=[ClaimVerdict(claim_no=1, verdict="unsupported", reason="x")],
                      unlisted_claims=[], signals_used=["Active Arabic social media accounts"])
    fake = FakeWriterClient([draft(), draft()], reviews=[bad, bad])
    email, _ = write(fake)
    assert email.status == "needs_review" and email.revisions == 1   # EMAIL_REVISIONS=1: no third try
    assert len(fake.writer_calls()) == 2


def test_no_review_means_step_4_behaviour():
    fake = FakeWriterClient([draft()])
    email, usage = write(fake, review=False)
    assert email.review is None and email.status == "ready"
    assert not [c for c in fake.parse_calls if c["text_format"] is EmailReview]


def test_arabic_site_is_searched_in_both_languages_and_translated_once():
    fake = FakeWriterClient([])
    profile = sample_profile()                                  # language "mixed"
    for _ in range(2):
        hits = writer.retrieve(kb_with_chunks(), LEAD, icp_report().segments[0], profile, client=fake)
    assert len(fake.create_calls) == 1                          # cached the second time
    assert "Arabic" in fake.create_calls[0]["instructions"]
    assert [c.id for c, _ in hits] == ["p1-c0", "p2-c0"]        # merged, best first, no duplicates

    english = profile.model_copy(update={"language": "en"})
    writer.retrieve(kb_with_chunks(), LEAD, icp_report().segments[0], english, client=fake)
    assert len(fake.create_calls) == 1                          # English site: no translation


def test_rules_name_unlisted_claims_and_the_strongest_signal():
    assert "Every sentence that says what the SENDER does" in writer.RULES
    assert "strongest buying signal" in writer.RULES
