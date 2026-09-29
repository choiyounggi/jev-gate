import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import eval as ev


def rec(item, question, agrees, conf, latency=100.0, error=None, kind="choice", task="t"):
    return {"task": task, "item_id": item, "question": question, "kind": kind,
            "agrees": agrees, "confidence": conf, "latency_ms": latency, "error": error}


def test_summarize_normal_case_computes_agreement_and_coverage():
    records = [
        rec("1", "q", True, 0.95),
        rec("2", "q", False, 0.55),
        rec("3", "q", True, 0.85),
        rec("4", "q", False, 0.9, error="boom"),
    ]
    s = ev.summarize(records, threshold=0.8)
    row = s["rows"][0]
    assert row["n"] == 4
    assert row["errors"] == 1
    assert row["agreement"] == pytest.approx(2 / 3)
    assert row["coverage_at_threshold"] == pytest.approx(2 / 3)
    assert row["agreement_when_confident"] == pytest.approx(1.0)
    assert s["calls"] == 3
    assert s["latency_ms_p50"] == 100.0


def test_summarize_empty_records_has_no_rows_and_no_division_error():
    s = ev.summarize([], threshold=0.8)
    assert s["rows"] == []
    assert s["calls"] == 0
    assert s["latency_ms_p50"] == 0.0


def test_summarize_rejects_threshold_outside_unit_interval():
    with pytest.raises(ValueError):
        ev.summarize([rec("1", "q", True, 0.9)], threshold=1.5)


def test_judge_noul_uses_half_as_decision_boundary_and_symmetric_confidence():
    pred, agrees, conf = ev.judge("noul", SimpleNamespace(noul=0.2), False)
    assert pred is False and agrees is True
    assert conf == pytest.approx(0.8)


def test_judge_choice_falls_back_to_max_probability_when_confidence_missing():
    ans = SimpleNamespace(choice="clear", probabilities={"clear": 0.7, "caution": 0.3})
    pred, agrees, conf = ev.judge("choice", ans, "caution")
    assert pred == "clear" and agrees is False
    assert conf == pytest.approx(0.7)


def test_judge_unknown_kind_raises():
    with pytest.raises(ValueError):
        ev.judge("essay", SimpleNamespace(), None)


def test_dataset_labels_cover_every_question_and_choice_labels_are_valid_options():
    data = json.loads((Path(ev.HERE) / "dataset.json").read_text(encoding="utf-8"))
    total = 0
    for task in data["tasks"].values():
        qs = task["questions"]
        for item in task["items"]:
            total += 1
            assert set(item["labels"]) == set(qs), item["id"]
            for qid, q in qs.items():
                label = item["labels"][qid]
                if q["type"] == "choice":
                    assert label in q["criteria"], (item["id"], qid)
                elif q["type"] == "score":
                    assert 0 <= label < len(q["criteria"]), (item["id"], qid)
                else:
                    assert isinstance(label, bool), (item["id"], qid)
    assert total == 50
