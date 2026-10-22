#!/usr/bin/env python3
"""Compare rule recommendations with a deliberately simple unstratified baseline."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.research import recommend


def baseline(videos, metrics):
    """Compare hook means if each group has any number; ignore provenance/sample size."""
    categories = {
        v["id"]: (v.get("analysis") or {}).get("hook_category") for v in videos
    }
    groups = {
        k: [
            r["retention_3s"]
            for r in metrics
            if categories.get(r["video_id"]) == k and r.get("retention_3s") is not None
        ]
        for k in ["preparation", "packaging"]
    }
    a, b = groups.values()
    return (
        "observational"
        if a and b and abs(sum(a) / len(a) - sum(b) / len(b)) > 1e-9
        else "exploratory"
    )


def run():
    fixture = json.loads((ROOT / "fixtures/evaluation.json").read_text())
    results = []
    for case in fixture["cases"]:
        recs = recommend(case["videos"], case["metrics"])
        rec = recs[0]
        expected = case["expected"]
        ids = {v["id"]: v for v in case["videos"]}
        refs = bool(rec["sources"]) and all(
            s["video_id"] in ids
            and 0 <= s["start"] < s["end"] <= ids[s["video_id"]]["duration"]
            for s in rec["sources"]
        )
        calculation = (
            expected["delta_pp"] is None
            and "delta_pp" not in rec["stats"]
            or expected["delta_pp"] is not None
            and abs(rec["stats"].get("delta_pp", 10000) - expected["delta_pp"]) < 1e-8
        )
        limits = any("causal" in x for x in rec["limitations"]) and (
            rec["kind"] != "exploratory"
            or any("not a data-supported" in x for x in rec["limitations"])
        )
        results.append(
            {
                "case": case["id"],
                "expected": expected["kind"],
                "actual": rec["kind"],
                "rule_correct": rec["kind"] == expected["kind"],
                "baseline_correct": baseline(case["videos"], case["metrics"])
                == expected["kind"],
                "references_correct": refs,
                "calculations_correct": calculation,
                "limitations_present": limits,
            }
        )
    report = {
        "scope": fixture["scope"],
        "provenance": fixture["provenance"],
        "baseline": "Unstratified hook mean difference; ignores provenance, denominator and repetition controls. Deliberately simple, not an industry benchmark.",
        "n": len(results),
        "scores": {
            key: sum(row[key] for row in results)
            for key in [
                "rule_correct",
                "baseline_correct",
                "references_correct",
                "calculations_correct",
                "limitations_present",
            ]
        },
        "cases": results,
    }
    print(json.dumps(report, indent=2))
    if not all(
        r["rule_correct"]
        and r["references_correct"]
        and r["calculations_correct"]
        and r["limitations_present"]
        for r in results
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    run()
