"""Tests for step 2 (agents/icp.py, scripts/define_icp.py). No API, no network.

Run:  pytest -v
"""
import json
import runpy
import sys
from types import SimpleNamespace

import pytest

import config
from agents import icp
from core import client as core_client
from core.schemas import ICPReport, ICPSegment
from tests.test_researcher import sample_profile


def segment(name="Saudi retail banks", priority="high"):
    return ICPSegment(
        name=name, description="Large banks with busy social channels.",
        industries=["Banking"], company_size="1,000-20,000 employees",
        regions=["Saudi Arabia"], buyer_roles=["Head of CX", "CMO"],
        pain_points=["Too many mentions to read by hand"],
        why_fit=["named_customers includes Al-Rajhi Bank"],
        signals=["Active Arabic X account"], disqualifiers=["No Arabic customers"],
        priority=priority,
    )


def report(summary="Initial proposal", names=("Saudi retail banks", "GCC telecoms")):
    return ICPReport(segments=[segment(n) for n in names], assumptions=[],
                     questions_for_user=["Which country first?"], change_summary=summary)


class FakeClient:
    """Returns the given reports in turn and records every request."""

    def __init__(self, *reports):
        self.reports = list(reports)
        self.calls = []
        self.responses = SimpleNamespace(parse=self._parse)

    def _parse(self, **params):
        self.calls.append(params)
        usage = SimpleNamespace(
            input_tokens=1200, output_tokens=900,
            input_tokens_details=SimpleNamespace(cached_tokens=0),
            output_tokens_details=SimpleNamespace(reasoning_tokens=640))
        return SimpleNamespace(id=f"resp_{len(self.calls)}", output=[], status="completed",
                               output_parsed=self.reports.pop(0), usage=usage)


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_FILE", str(tmp_path / "calls.jsonl"))
    monkeypatch.setattr(config, "REASONING_EFFORT", "medium")


# --- agents/icp.py ---------------------------------------------------------

def test_propose_sends_profile_to_reasoning_model():
    fake = FakeClient(report())
    result, response = icp.propose_icp(sample_profile(), client=fake)

    assert result.segments[0].name == "Saudi retail banks"
    [call] = fake.calls
    assert call["model"] == config.model_for("reasoning")
    assert call["reasoning"] == {"effort": "medium"}
    assert call["text_format"] is ICPReport
    assert call["store"] is True
    assert "temperature" not in call  # reasoning models reject it
    assert "previous_response_id" not in call
    assert '"name": "Acme Logistics"' in call["input"]


def test_refine_sends_only_feedback_plus_previous_id():
    fake = FakeClient(report("Focused on banks"))
    icp.refine_icp("Focus on banks only", "resp_1", client=fake)

    [call] = fake.calls
    assert call["input"] == "Focus on banks only"          # not the whole profile again
    assert call["previous_response_id"] == "resp_1"
    # Not carried over by the server, so sent again on every turn:
    assert call["instructions"] == icp.INSTRUCTIONS
    assert call["text_format"] is ICPReport


def test_reasoning_param_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(config, "REASONING_EFFORT", None)
    fake = FakeClient(report())
    icp.propose_icp(sample_profile(), client=fake)
    assert "reasoning" not in fake.calls[0]


def test_reasoning_tokens_are_logged(tmp_path):
    icp.propose_icp(sample_profile(), client=FakeClient(report()))
    line = json.loads((tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["reasoning_tokens"] == 640
    assert line["task"] == "reasoning"


def test_incomplete_answer_suggests_lower_effort():
    fake = FakeClient(None)
    with pytest.raises(RuntimeError, match="REASONING_EFFORT=low"):
        icp.propose_icp(sample_profile(), client=fake)


def test_load_profile_errors_are_clear(tmp_path):
    with pytest.raises(FileNotFoundError, match="Run step 1 first"):
        icp.load_profile(tmp_path / "missing.json")
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"name": "X", "target_customers": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="older step"):
        icp.load_profile(old)


# --- scripts/define_icp.py, end to end with a fake model --------------------

def test_script_runs_proposal_and_feedback_and_saves_versions(tmp_path, monkeypatch):
    out = tmp_path / "data" / "output"
    out.mkdir(parents=True)
    (out / "company_acme.example.json").write_text(sample_profile().model_dump_json(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    fake = FakeClient(report(), report("Focused on banks", names=("Saudi retail banks",)))
    monkeypatch.setattr(core_client, "_client", fake)
    monkeypatch.setattr(sys, "argv", ["define_icp", "acme.example", "--feedback", "Focus on banks"])

    runpy.run_module("scripts.define_icp", run_name="__main__")

    assert (out / "icp_acme.example_v1.json").is_file()
    assert (out / "icp_acme.example_v2.json").is_file()
    final = json.loads((out / "icp_acme.example.json").read_text(encoding="utf-8"))
    assert final["change_summary"] == "Focused on banks"
    assert len(final["segments"]) == 1
    # the second turn pointed at the first response
    assert fake.calls[1]["previous_response_id"] == "resp_1"
    monkeypatch.setattr(core_client, "_client", None)
