"""Exercise the running localhost app using only its synthetic demo workspace.

Creates a new experiment on each run. No paid API or external publication.
Start the seeded server on 127.0.0.1:8770 first.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "/api/workspaces/demo-coffee"


def main() -> None:
    # This acceptance client is restricted to the local demo server, not a proxy.
    with httpx.Client(base_url="http://127.0.0.1:8770", timeout=20, trust_env=False) as client:

        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response

        request(
            "POST",
            "/api/login",
            json={"email": "demo@example.test", "password": "creative-demo"},
        )
        candidate = request("GET", BASE + "/recommendations").json()[0]
        body = {
            key: candidate[key]
            for key in (
                "hypothesis",
                "change",
                "preserve",
                "metric",
                "threshold_pp",
                "min_views",
                "window_days",
                "limitations",
            )
        }
        body.update(
            title="Preparation opening · verified export",
            baseline_id="demo-video-1",
            recommendation_id=candidate["id"],
        )
        experiment = request("POST", BASE + "/experiments", json=body).json()
        path = BASE + "/experiments/" + experiment["id"]
        operation = request(
            "POST",
            path + "/edit",
            data={"start": "0", "end": "2"},
            files={
                "file": (
                    "replacement.mp4",
                    (ROOT / "fixtures/demo/replacement.mp4").read_bytes(),
                    "video/mp4",
                )
            },
        ).json()
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            operation = next(
                op
                for op in request("GET", BASE + "/operations").json()
                if op["id"] == operation["id"]
            )
            if operation["status"] not in ("pending", "running"):
                break
            time.sleep(0.1)
        assert operation["status"] == "completed", operation
        timing = operation["result"]["report"]["timing"]
        assert timing["verified"] and timing["video_duration_seconds"] == 8
        request("PATCH", path, json={"status": "ready"})
        request("PATCH", path, json={"status": "awaiting"})
        csv = request("GET", path + "/csv-template").content
        first = request(
            "POST", BASE + "/import", files={"file": ("results.csv", csv, "text/csv")}
        ).json()
        repeated = request(
            "POST", BASE + "/import", files={"file": ("results.csv", csv, "text/csv")}
        ).json()
        assert first["inserted"] == 1 and first["duplicate"] == 1, first
        assert repeated["inserted"] == 0 and repeated["duplicate"] == 2, repeated
        result = request("POST", path + "/evaluate", json={}).json()
        assert (
            result["outcome"] == "observed_improvement"
            and abs(result["delta_pp"] - 9) < 1e-9
        ), result
        assert any(
            item["id"] == experiment["id"]
            for item in request("GET", BASE + "/knowledge").json()
        )
        report = {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "kind": "synthetic localhost HTTP acceptance walkthrough",
            "live_api_calls": 0,
            "experiment_id": experiment["id"],
            "url": "http://127.0.0.1:8770/#experiment/" + experiment["id"],
            "first_import": {key: first[key] for key in ("inserted", "duplicate")},
            "repeated_import": {
                key: repeated[key] for key in ("inserted", "duplicate")
            },
            "edit_report": operation["result"]["report"],
            "evaluation": result,
            "knowledge_record_found": True,
        }
        output = ROOT / "artifacts/verification/demo_flow.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(report["url"])
        print(
            "PASS: edit, exact timing, CSV repeat, evaluation and knowledge persistence"
        )


if __name__ == "__main__":
    main()
