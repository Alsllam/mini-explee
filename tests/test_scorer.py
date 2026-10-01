"""Tests for step 3 (agents/scorer.py, scripts/score_leads.py, scripts/make_leads.py).
No API, no network: fake clients stand in for OpenAI / Azure.

Run:  pytest -v
"""
import csv
import json
import runpy
import sys
from types import SimpleNamespace

import pytest

import config
from agents import scorer
from core import client as core_client
from core.cost import Usage, estimate_usd
from tests.test_icp import report as icp_report

LEADS = [
    {"lead_id": "L001", "company": "Zarnub Bank", "industry": "Banking", "country": "Saudi Arabia",
     "city": "Riyadh", "employees": "4200", "website": "zarnubbank.example",
     "description": "Zarnub Bank is a banking company.", "signals": "Active Arabic social media accounts"},
    {"lead_id": "L002", "company": "Temvor Petroleum", "industry": "Oil and gas", "country": "Germany",
     "city": "Berlin", "employees": "30", "website": "temvorpetroleum.example",
     "description": "Temvor Petroleum serves other businesses.", "signals": "No social media presence"},
]


def score_json(lead_id, score, segment="Saudi retail banks", rec="contact"):
    return json.dumps({"lead_id": lead_id, "segment": segment, "fit_score": score,
                       "reasons": ["industry: Banking"], "missing_info": [], "recommendation": rec})


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_FILE", str(tmp_path / "calls.jsonl"))
    monkeypatch.setattr(config, "IS_AZURE", False)
    monkeypatch.setattr(config, "MODEL_BATCH", None)
    monkeypatch.setattr(scorer, "SCORING_TEMPERATURE", 0.0)


# --- the request -------------------------------------------------------------

def test_prefix_is_identical_and_lead_comes_last():
    icp = icp_report()
    a = scorer.build_request(LEADS[0], icp, "m", cache_key="icp-x")
    b = scorer.build_request(LEADS[1], icp, "m", cache_key="icp-x")

    assert a["instructions"] == b["instructions"]          # cacheable prefix (lesson 2.4)
    assert a["instructions"].startswith(scorer.RUBRIC)
    assert "Saudi retail banks" in a["instructions"]        # the ICP is in the prefix
    assert a["input"] != b["input"] and "Zarnub Bank" in a["input"]
    assert a["temperature"] == 0.0
    assert a["prompt_cache_key"] == "icp-x"


def test_text_format_is_a_strict_json_schema():
    fmt = scorer.text_format()["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True
    assert set(fmt["schema"]["required"]) == set(fmt["schema"]["properties"])
    json.dumps(fmt)  # plain JSON: can go into a batch file


def test_no_cache_key_on_azure(monkeypatch):
    monkeypatch.setattr(config, "IS_AZURE", True)
    body = scorer.build_request(LEADS[0], icp_report(), "m", cache_key="icp-x")
    assert "prompt_cache_key" not in body


def test_parse_score_clamps_and_fixes_recommendation():
    s = scorer.parse_score(score_json("WRONG", 140, rec="skip"), "L001")
    assert s.lead_id == "L001" and s.fit_score == 100 and s.recommendation == "contact"
    assert scorer.parse_score(score_json("L1", 55, rec="contact"), "L1").recommendation == "nurture"


# --- direct mode -------------------------------------------------------------

class FakeDirect:
    def __init__(self):
        self.calls = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **params):
        self.calls.append(params)
        lead_id = params["input"].split("lead_id: ")[1].split("\n")[0]
        usage = SimpleNamespace(input_tokens=2000, output_tokens=60,
                                input_tokens_details=SimpleNamespace(cached_tokens=1792),
                                output_tokens_details=SimpleNamespace(reasoning_tokens=0))
        score = 85 if lead_id == "L001" else 5
        return SimpleNamespace(id="r", output_text=score_json(lead_id, score), usage=usage, status="completed")


def test_score_direct_keeps_order_and_sums_usage():
    fake = FakeDirect()
    scores, usage = scorer.score_direct(LEADS, icp_report(), workers=2, client=fake)

    assert [s.lead_id for s in scores] == ["L001", "L002"]
    assert scores[1].recommendation == "skip"
    assert usage.requests == 2 and usage.input_tokens == 4000 and usage.cached_tokens == 3584
    assert fake.calls[0]["model"] == config.model_for("fast")
    assert fake.calls[0]["text"]["format"]["name"] == "LeadScore"


# --- batch mode --------------------------------------------------------------

def test_batch_file_has_one_request_per_line(tmp_path):
    path = scorer.write_batch_file(LEADS, icp_report(), tmp_path / "in.jsonl")
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert [line["custom_id"] for line in lines] == ["L001", "L002"]
    assert all(line["method"] == "POST" and line["url"] == "/v1/responses" for line in lines)
    assert lines[0]["body"]["model"] == config.model_for("fast")


def test_azure_batch_needs_its_own_deployment(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IS_AZURE", True)
    with pytest.raises(ValueError, match="Global Batch"):
        scorer.write_batch_file(LEADS, icp_report(), tmp_path / "in.jsonl")
    monkeypatch.setattr(config, "MODEL_BATCH", "gpt-4o-mini-batch")
    path = scorer.write_batch_file(LEADS, icp_report(), tmp_path / "in.jsonl")
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[0])["body"]["model"] == "gpt-4o-mini-batch"


def batch_output_line(lead_id, score, ok=True):
    if not ok:
        return json.dumps({"custom_id": lead_id, "response": {"status_code": 400, "body": {
            "error": {"message": "bad request"}}}, "error": None})
    body = {"output": [{"type": "message", "content": [{"type": "output_text", "text": score_json(lead_id, score)}]}],
            "usage": {"input_tokens": 2000, "output_tokens": 60, "input_tokens_details": {"cached_tokens": 0}}}
    return json.dumps({"custom_id": lead_id, "response": {"status_code": 200, "body": body}, "error": None})


def test_read_batch_output_matches_by_custom_id_and_collects_errors():
    text = "\n".join([batch_output_line("L002", 5), batch_output_line("L001", 88),
                      batch_output_line("L003", 0, ok=False)])
    scores, usage, errors = scorer.read_batch_output(text)

    assert {s.lead_id: s.fit_score for s in scores} == {"L002": 5, "L001": 88}
    assert usage.requests == 2
    assert errors[0]["lead_id"] == "L003"


class FakeBatchClient:
    """Files + batches endpoints; the batch completes on the first retrieve."""

    def __init__(self, output_text):
        self.uploaded = []
        self.created = []
        self.output_text = output_text
        self.files = SimpleNamespace(create=self._upload, content=self._content)
        self.batches = SimpleNamespace(create=self._create, retrieve=self._retrieve)

    def _upload(self, file, purpose):
        self.uploaded.append((file.read(), purpose))
        return SimpleNamespace(id="file_in")

    def _create(self, **params):
        self.created.append(params)
        return SimpleNamespace(id="batch_1", status="validating")

    def _retrieve(self, batch_id):
        return SimpleNamespace(id=batch_id, status="completed", output_file_id="file_out", error_file_id=None,
                               errors=None, request_counts=SimpleNamespace(completed=2, failed=0, total=2))

    def _content(self, file_id):
        return SimpleNamespace(text=self.output_text)


def test_submit_uploads_then_creates_batch(tmp_path):
    path = scorer.write_batch_file(LEADS, icp_report(), tmp_path / "in.jsonl")
    fake = FakeBatchClient("")
    batch = scorer.submit_batch(path, client=fake)

    assert batch.id == "batch_1"
    assert fake.uploaded[0][1] == "batch"
    assert fake.created[0]["input_file_id"] == "file_in"
    assert fake.created[0]["endpoint"] == "/v1/responses"
    assert fake.created[0]["completion_window"] == "24h"


# --- cost --------------------------------------------------------------------

def test_batch_costs_half_and_cached_tokens_cost_less(monkeypatch):
    for k in ("PRICE_INPUT_PER_M", "PRICE_CACHED_PER_M", "PRICE_OUTPUT_PER_M"):
        monkeypatch.delenv(k, raising=False)
    plain = Usage(input_tokens=1_000_000, cached_tokens=0, output_tokens=0, requests=1)
    cached = Usage(input_tokens=1_000_000, cached_tokens=1_000_000, output_tokens=0, requests=1)
    assert estimate_usd(plain, "gpt-4o-mini") == pytest.approx(0.15)
    assert estimate_usd(plain, "gpt-4o-mini", batch=True) == pytest.approx(0.075)
    assert estimate_usd(cached, "gpt-4o-mini") < estimate_usd(plain, "gpt-4o-mini")


# --- make_leads ---------------------------------------------------------------

def test_make_leads_is_fictional_and_repeatable(tmp_path, monkeypatch):
    out1, out2 = tmp_path / "a.csv", tmp_path / "b.csv"
    for out in (out1, out2):
        monkeypatch.setattr(sys, "argv", ["make_leads", "--n", "30", "--out", str(out)])
        runpy.run_module("scripts.make_leads", run_name="__main__")
    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
    rows = list(csv.DictReader(out1.open(encoding="utf-8")))
    assert len(rows) == 30 and all(r["website"].endswith(".example") for r in rows)
    assert len({r["company"] for r in rows}) == 30


# --- the script, end to end ---------------------------------------------------

@pytest.fixture
def project(tmp_path, monkeypatch):
    out = tmp_path / "data" / "output"
    out.mkdir(parents=True)
    (out / "icp_acme.example.json").write_text(icp_report().model_dump_json(), encoding="utf-8")
    with (tmp_path / "data" / "leads_sample.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(LEADS[0]))
        writer.writeheader()
        writer.writerows(LEADS)
    monkeypatch.chdir(tmp_path)
    yield out
    monkeypatch.setattr(core_client, "_client", None)


def run_script(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["score_leads", "acme.example", *argv])
    try:
        runpy.run_module("scripts.score_leads", run_name="__main__")
    except SystemExit as done:  # the script ends some paths with SystemExit(0)
        assert done.code in (0, None)


def test_script_direct(project, monkeypatch, capsys):
    monkeypatch.setattr(core_client, "_client", FakeDirect())
    run_script(monkeypatch, "--mode", "direct")

    rows = list(csv.DictReader((project / "leads_scored_acme.example_direct.csv").open(encoding="utf-8-sig")))
    assert rows[0]["lead_id"] == "L001" and rows[0]["recommendation"] == "contact"
    printed = capsys.readouterr().out
    assert "1 contact, 0 nurture, 1 skip" in printed and "Batch API" in printed


def test_script_batch_submit_then_check(project, monkeypatch, capsys):
    fake = FakeBatchClient("\n".join([batch_output_line("L001", 90), batch_output_line("L002", 10)]))
    monkeypatch.setattr(core_client, "_client", fake)

    run_script(monkeypatch, "--mode", "batch")
    state = json.loads((project / "batch_acme.example.json").read_text(encoding="utf-8"))
    assert state["batch_id"] == "batch_1" and state["leads"] == 2

    run_script(monkeypatch, "--check")
    rows = list(csv.DictReader((project / "leads_scored_acme.example_batch.csv").open(encoding="utf-8-sig")))
    assert [r["lead_id"] for r in rows] == ["L001", "L002"]
    assert "completed" in capsys.readouterr().out


def test_script_batch_dry_run_submits_nothing(project, monkeypatch):
    fake = FakeBatchClient("")
    monkeypatch.setattr(core_client, "_client", fake)
    run_script(monkeypatch, "--mode", "batch", "--dry-run")
    assert (project / "batch_input_acme.example.jsonl").is_file()
    assert fake.uploaded == [] and fake.created == []


def test_batch_refuses_a_key_in_model_batch(tmp_path, monkeypatch):
    secret = "jKbM0djrnsxzXnf1L6ETtzWmawqkZziaX7NmYCJ5O9azLqC9i35bXs5LcKmYnwXGVzBxco4piNarYnSQD9e9"
    monkeypatch.setattr(config, "IS_AZURE", True)
    monkeypatch.setattr(config, "MODEL_BATCH", secret)
    with pytest.raises(ValueError, match="MODEL_BATCH") as err:
        scorer.write_batch_file(LEADS, icp_report(), tmp_path / "in.jsonl")
    assert secret not in str(err.value)
    assert not (tmp_path / "in.jsonl").exists()  # nothing written to disk
