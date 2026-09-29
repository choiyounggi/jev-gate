"""Measure how well a Jev-compatible decision model agrees with hand labels.

Usage (local ollaya):
    TYPESAFE_API_KEY=local TYPESAFE_BASE_URL=http://localhost:11435 \
        uv run --with typesafe-sdk python eval.py --model laya

Usage (hosted Jev, once a key exists):
    TYPESAFE_API_KEY=ts_... uv run --with typesafe-sdk python eval.py --model jev-latest

The official SDK is used on purpose: it proves the local server is a drop-in.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_THRESHOLD = 0.8


def build_questions(spec: dict) -> dict:
    from typesafe_sdk import Choice, Noul, Score

    out = {}
    for qid, q in spec.items():
        kind = q["type"]
        if kind == "choice":
            out[qid] = Choice(instructions=q.get("instructions"), criteria=q["criteria"])
        elif kind == "noul":
            out[qid] = Noul(instructions=q.get("instructions"), criteria=q.get("criteria"))
        elif kind == "score":
            out[qid] = Score(instructions=q.get("instructions"), criteria=q["criteria"])
        else:
            raise ValueError(f"unknown question type {kind!r} for {qid}")
    return out


def judge(kind: str, answer, label) -> tuple[object, bool, float]:
    """Return (predicted, agrees_with_label, confidence) for one answer."""
    if kind == "choice":
        probs = dict(getattr(answer, "probabilities", {}) or {})
        conf = getattr(answer, "confidence", None)
        if conf is None:
            conf = max(probs.values()) if probs else 0.0
        return answer.choice, answer.choice == label, float(conf)
    if kind == "noul":
        p = float(answer.noul)
        pred = p >= 0.5
        return pred, pred == bool(label), max(p, 1.0 - p)
    if kind == "score":
        s = float(answer.score)
        pred = int(round(s))
        probs = dict(getattr(answer, "probabilities", {}) or {})
        conf = getattr(answer, "confidence", None)
        if conf is None:
            conf = max(probs.values()) if probs else 0.0
        return pred, pred == int(label), float(conf)
    raise ValueError(f"unknown question type {kind!r}")


def summarize(records: list[dict], threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Aggregate per-question agreement, latency and coverage at a confidence threshold.

    records: one dict per (item, question) with keys
        task, question, kind, agrees (bool), confidence (float), latency_ms (float), error (str|None)
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be within [0, 1]")
    by_q: dict[tuple[str, str], list[dict]] = {}
    for r in records:
        by_q.setdefault((r["task"], r["question"]), []).append(r)

    rows = []
    for (task, question), rs in sorted(by_q.items()):
        ok = [r for r in rs if not r.get("error")]
        errors = len(rs) - len(ok)
        agreed = sum(1 for r in ok if r["agrees"])
        confident = [r for r in ok if r["confidence"] >= threshold]
        confident_agreed = sum(1 for r in confident if r["agrees"])
        rows.append(
            {
                "task": task,
                "question": question,
                "kind": ok[0]["kind"] if ok else rs[0]["kind"],
                "n": len(rs),
                "errors": errors,
                "agreement": agreed / len(ok) if ok else 0.0,
                "coverage_at_threshold": len(confident) / len(ok) if ok else 0.0,
                "agreement_when_confident": confident_agreed / len(confident) if confident else 0.0,
            }
        )

    latencies = sorted({r["item_id"]: r["latency_ms"] for r in records if not r.get("error")}.values())
    return {
        "threshold": threshold,
        "rows": rows,
        "calls": len(latencies),
        "latency_ms_p50": statistics.median(latencies) if latencies else 0.0,
        "latency_ms_max": max(latencies) if latencies else 0.0,
    }


def render_markdown(model: str, summary: dict, disagreements: list[dict]) -> str:
    lines = [
        f"# {model}",
        "",
        f"calls: {summary['calls']}, latency p50 {summary['latency_ms_p50']:.0f} ms, max {summary['latency_ms_max']:.0f} ms, threshold {summary['threshold']}",
        "",
        "| task | question | kind | n | agreement | coverage@thr | agreement when confident | errors |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in summary["rows"]:
        lines.append(
            f"| {r['task']} | {r['question']} | {r['kind']} | {r['n']} | {r['agreement']:.0%} | "
            f"{r['coverage_at_threshold']:.0%} | {r['agreement_when_confident']:.0%} | {r['errors']} |"
        )
    lines += ["", "## Disagreements", ""]
    if not disagreements:
        lines.append("(none)")
    for d in disagreements:
        lines.append(
            f"- {d['item_id']} `{d['question']}`: label={d['label']!r} predicted={d['predicted']!r} "
            f"conf={d['confidence']:.2f} — {d['state_preview']}"
        )
    return "\n".join(lines) + "\n"


def run(model: str, dataset_path: Path, threshold: float, out_dir: Path) -> int:
    from typesafe_sdk import TypeSafeClient, TypeSafeError

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    tasks = data.get("tasks") or {}
    if not tasks:
        print("dataset has no tasks", file=sys.stderr)
        return 2

    # A cold model load on ollaya (8 GB winnow:e4b) takes longer than the SDK's 10 s default.
    client = TypeSafeClient(timeout=120.0)
    try:
        from typesafe_sdk import Noul as _Noul

        t0 = time.perf_counter()
        client.system_one("warmup", {"ok": _Noul(instructions="The state is the word warmup.")}, model=model)
        print(f"warmup {(time.perf_counter() - t0) * 1000:6.0f} ms (model load, excluded from stats)", file=sys.stderr)
    except TypeSafeError as e:
        print(f"warmup failed: {e}", file=sys.stderr)
        return 1
    records: list[dict] = []
    disagreements: list[dict] = []
    for task_name, task in tasks.items():
        questions = build_questions(task["questions"])
        kinds = {qid: q["type"] for qid, q in task["questions"].items()}
        for item in task["items"]:
            t0 = time.perf_counter()
            try:
                resp = client.system_one(item["state"], questions, model=model)
                err = None
            except TypeSafeError as e:
                resp, err = None, f"{type(e).__name__}: {e}"
            latency_ms = (time.perf_counter() - t0) * 1000
            preview = json.dumps(item["state"], ensure_ascii=False)[:90]
            for qid, kind in kinds.items():
                label = item["labels"][qid]
                if err is not None:
                    records.append(
                        {"task": task_name, "item_id": item["id"], "question": qid, "kind": kind,
                         "agrees": False, "confidence": 0.0, "latency_ms": latency_ms, "error": err}
                    )
                    continue
                answer = resp.answers.get(qid)
                if answer is None:
                    records.append(
                        {"task": task_name, "item_id": item["id"], "question": qid, "kind": kind,
                         "agrees": False, "confidence": 0.0, "latency_ms": latency_ms,
                         "error": "answer missing from response"}
                    )
                    continue
                predicted, agrees, conf = judge(kind, answer, label)
                records.append(
                    {"task": task_name, "item_id": item["id"], "question": qid, "kind": kind,
                     "agrees": agrees, "confidence": conf, "latency_ms": latency_ms, "error": None,
                     "label": label, "predicted": predicted, "model_resolved": resp.model}
                )
                if not agrees:
                    disagreements.append(
                        {"item_id": item["id"], "question": qid, "label": label,
                         "predicted": predicted, "confidence": conf, "state_preview": preview}
                    )
            print(f"{item['id']} {latency_ms:6.0f} ms {'ERROR ' + err if err else ''}", file=sys.stderr)

    summary = summarize(records, threshold)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_model = model.replace(":", "_").replace("/", "_")
    (out_dir / f"{safe_model}-{stamp}.json").write_text(
        json.dumps({"model": model, "summary": summary, "records": records}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    md = render_markdown(model, summary, disagreements)
    (out_dir / f"{safe_model}-{stamp}.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True, help="model name, e.g. laya, winnow:e4b, jev-latest")
    p.add_argument("--dataset", type=Path, default=HERE / "dataset.json")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    p.add_argument("--out", type=Path, default=HERE / "results")
    a = p.parse_args(argv)
    return run(a.model, a.dataset, a.threshold, a.out)


if __name__ == "__main__":
    sys.exit(main())
