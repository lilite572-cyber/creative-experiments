"""HTTP contract and persistence checks; no external model calls."""

import csv
import io
import os
import re
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import db
from app.main import app
from app.media import make_demo
from app.research import CSV_COLUMNS


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_dir = tempfile.TemporaryDirectory()
        cls.video = Path(cls.media_dir.name) / "sample.mp4"
        cls.replacement = Path(cls.media_dir.name) / "replacement.mp4"
        make_demo(cls.video, hook="packaging", duration=4)
        make_demo(cls.replacement, hook="preparation", duration=2)

    @classmethod
    def tearDownClass(cls):
        cls.media_dir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root_patch = patch.object(db, "ROOT", Path(self.tmp.name))
        self.root_patch.start()
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("CE_OPENAI_APPROVED_BUDGET_USD", None)
        self.client = TestClient(app)
        self.client.__enter__()
        self.credentials = {
            "email": "owner@example.test",
            "password": "strong-test-password",
        }
        self.assertEqual(
            self.client.post("/api/register", json=self.credentials).status_code, 200
        )
        self.wid = self.client.post(
            "/api/workspaces", json={"name": "Test brand"}
        ).json()["id"]
        self.base = f"/api/workspaces/{self.wid}"

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        self.root_patch.stop()
        self.tmp.cleanup()

    def upload(self, client=None, base=None, data=None):
        result = (client or self.client).post(
            (base or self.base) + "/videos",
            data={"title": "Coffee source"},
            files={
                "file": (
                    "sample.mp4",
                    data if data is not None else self.video.read_bytes(),
                    "video/mp4",
                )
            },
        )
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def wait_op(self, op):
        for _ in range(200):
            rows = self.client.get(self.base + "/operations").json()
            found = next(r for r in rows if r["id"] == op["id"])
            if found["status"] not in ("pending", "running"):
                return found
            time.sleep(0.025)
        self.fail("Operation did not finish")

    def csv_text(self, rows):
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        return out.getvalue()

    def metric(self, vid, pub="post-1", retention=".40", views="1000"):
        return dict(
            publication_id=pub,
            video_id=vid,
            platform="instagram",
            traffic="organic",
            source="manual-test",
            period_start="2026-10-01",
            period_end="2026-10-08",
            views=views,
            retention_3s=retention,
            retention_unit="fraction",
        )

    def import_rows(self, rows):
        return self.client.post(
            self.base + "/import",
            files={"file": ("metrics.csv", self.csv_text(rows), "text/csv")},
        )

    def create_experiment(self, vid):
        result = self.client.post(
            self.base + "/experiments",
            json=dict(
                title="Opening test",
                hypothesis="Preparation opening improves retention",
                baseline_id=vid,
                change="Replace first two seconds",
                preserve=["remaining video", "original audio"],
                threshold_pp=5,
                min_views=100,
                window_days=7,
            ),
        )
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_home_references_served_stylesheet_and_script(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        assets = set(re.findall(r'(?:src|href)="([^"]+\.(?:css|js))"', response.text))
        self.assertEqual(assets, {"/static/styles.css", "/static/app.js"})
        web = Path(__file__).resolve().parents[1] / "web"
        for url in assets:
            with self.subTest(url=url):
                asset = self.client.get(url)
                self.assertEqual(asset.status_code, 200)
                self.assertEqual(asset.content, (web / Path(url).name).read_bytes())
                self.assertTrue(asset.content)
                expected = "text/css" if url.endswith(".css") else "javascript"
                self.assertIn(expected, asset.headers["content-type"])

    def test_restart_interrupts_persisted_work_without_retrying(self):
        self.client.__exit__(None, None, None)
        original = {}
        with db.connect() as c:
            for status in ("pending", "running"):
                op = {
                    "id": db.uid(),
                    "kind": "analysis",
                    "status": status,
                    "input": {"video_id": "saved-video", "mode": "openai"},
                    "result": None,
                    "error": None,
                    "cost_usd": None,
                    "reservation_usd": 0.1,
                    "budget_halted": True,
                    "created_at": db.now(),
                }
                original[op["id"]] = op
                db.save(c, self.wid, "operation", op)
        with (
            patch("app.main.POOL.submit") as submit,
            patch("app.provider.analyze") as analyze,
        ):
            self.client = TestClient(app)
            self.client.__enter__()
            self.assertEqual(
                self.client.post("/api/login", json=self.credentials).status_code, 200
            )
            recovered = self.client.get(self.base + "/operations").json()
            self.assertEqual({op["id"] for op in recovered}, set(original))
            for op in recovered:
                with self.subTest(previous_status=original[op["id"]]["status"]):
                    expected = original[op["id"]]
                    self.assertEqual(op["status"], "interrupted")
                    self.assertIn("Outcome unknown", op["error"])
                    for key in (
                        "input",
                        "created_at",
                        "result",
                        "cost_usd",
                        "reservation_usd",
                        "budget_halted",
                    ):
                        self.assertEqual(op[key], expected[key])
            submit.assert_not_called()
            analyze.assert_not_called()
        with db.connect() as c:
            self.assertTrue(
                all(
                    op["status"] == "interrupted"
                    for op in db.rows(c, self.wid, "operation")
                )
            )

    def test_auth_and_cross_workspace_scope(self):
        video = self.upload()
        exp = self.create_experiment(video["id"])
        other = TestClient(app)
        self.assertEqual(other.get(self.base + "/videos").status_code, 401)
        self.assertEqual(
            other.post(
                "/api/register",
                json={"email": "other@example.test", "password": "other-test-password"},
            ).status_code,
            200,
        )
        own = other.post("/api/workspaces", json={"name": "Other"}).json()["id"]
        for path in [
            "/videos",
            "/recommendations",
            "/operations",
            "/knowledge",
            "/experiments/" + exp["id"],
            "/videos/" + video["id"] + "/media",
        ]:
            self.assertEqual(other.get(self.base + path).status_code, 404, path)
        self.assertEqual(
            other.get(
                f"/api/workspaces/{own}/videos/" + video["id"] + "/media"
            ).status_code,
            404,
        )
        self.assertEqual(
            other.post(
                f"/api/workspaces/{own}/experiments",
                json=dict(
                    title="Invalid",
                    hypothesis="No access",
                    baseline_id=video["id"],
                    change="Change",
                ),
            ).status_code,
            404,
        )
        other.close()
        self.assertEqual(self.client.post("/api/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        self.assertEqual(
            self.client.post("/api/login", json=self.credentials).status_code, 200
        )
        self.assertEqual(
            self.client.get(self.base + "/videos").json()[0]["id"], video["id"]
        )

    def test_csv_atomic_duplicate_missing_and_foreign_video(self):
        vid = self.upload()["id"]
        good = self.metric(vid, retention="", views="")
        bad = self.metric("foreign-video", pub="post-2")
        self.assertEqual(self.import_rows([good, bad]).status_code, 422)
        self.assertEqual(
            self.client.get(self.base + "/videos").json()[0]["metrics"], []
        )
        first = self.import_rows([good])
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["inserted"], 1)
        repeat = self.import_rows([good])
        self.assertEqual(repeat.json()["inserted"], 0)
        self.assertEqual(repeat.json()["duplicate"], 1)
        metric = self.client.get(self.base + "/videos").json()[0]["metrics"][0]
        self.assertIsNone(metric["views"])
        self.assertIsNone(metric["retention_3s"])
        conflict = dict(good, views="200")
        self.assertEqual(self.import_rows([conflict]).status_code, 422)
        malformed = self.client.post(
            self.base + "/import",
            files={"file": ("bad.csv", "video_id,wrong\nx,1", "text/csv")},
        )
        self.assertEqual(malformed.status_code, 422)

    def test_bad_video_and_live_analysis_gate(self):
        response = self.client.post(
            self.base + "/videos",
            data={"title": "Bad"},
            files={"file": ("bad.mp4", b"not-video", "video/mp4")},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(self.base + "/videos").json(), [])
        self.assertEqual(list((db.ROOT / self.wid).glob("*.mp4")), [])
        video = self.upload()
        gate = self.client.post(
            self.base + "/videos/" + video["id"] + "/analyze", json={"mode": "openai"}
        )
        self.assertEqual(gate.status_code, 403)
        self.assertEqual(self.client.get(self.base + "/operations").json(), [])

    def test_local_analysis_and_provider_failure_recorded(self):
        video = self.upload()
        route = self.base + "/videos/" + video["id"] + "/analyze"
        job = self.client.post(route, json={"mode": "local"})
        self.assertEqual(job.status_code, 200, job.text)
        completed = self.wait_op(job.json())
        self.assertEqual(completed["status"], "completed", completed)
        self.assertEqual(completed["cost_usd"], 0)
        analysis = self.client.get(self.base + "/videos").json()[0]["analysis"]
        self.assertEqual(analysis["mode"], "local")
        self.assertEqual(analysis["hook_category"], "unknown")
        os.environ["CE_OPENAI_APPROVED_BUDGET_USD"] = "1"
        os.environ["OPENAI_API_KEY"] = "test-secret-not-live"
        with patch(
            "app.provider.analyze",
            side_effect=ValueError("provider timeout test-secret-not-live"),
        ):
            job = self.client.post(route, json={"mode": "openai"})
            self.assertEqual(job.status_code, 200, job.text)
            failed = self.wait_op(job.json())
        self.assertEqual(failed["status"], "failed")
        self.assertNotIn("test-secret-not-live", failed["error"])
        self.assertIn("timeout", failed["error"])
        self.assertIsNone(failed["cost_usd"])
        self.assertEqual(
            self.client.get(self.base + "/videos").json()[0]["analysis"]["mode"],
            "local",
        )

    def test_full_edit_freeze_evaluate_history_survives_restart(self):
        video = self.upload()
        exp = self.create_experiment(video["id"])
        url = self.base + "/experiments/" + exp["id"]
        self.assertEqual(
            self.client.patch(url, json={"status": "ready"}).status_code, 409
        )
        edit = self.client.post(
            url + "/edit",
            data={"start": "0", "end": "2"},
            files={
                "file": ("replacement.mp4", self.replacement.read_bytes(), "video/mp4")
            },
        )
        self.assertEqual(edit.status_code, 200, edit.text)
        result = self.wait_op(edit.json())
        self.assertEqual(result["status"], "completed", result)
        exp = self.client.get(url).json()
        self.assertIsNotNone(exp["variant_id"])
        self.assertEqual(
            self.client.patch(url, json={"status": "ready"}).status_code, 200
        )
        frozen = self.client.patch(url, json={"status": "awaiting"}).json()[
            "frozen_criteria"
        ]
        self.assertEqual(frozen["threshold_pp"], 5)
        imported = self.import_rows(
            [
                self.metric(video["id"]),
                self.metric(exp["variant_id"], pub="post-2", retention=".44"),
            ]
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertFalse(self.client.get(url).json()["results_present_at_freeze"])
        repeated = self.client.patch(url, json={"status": "awaiting"}).json()
        self.assertFalse(repeated["results_present_at_freeze"])
        self.assertEqual(repeated["frozen_criteria"], frozen)
        changed = self.client.patch(url, json={"threshold_pp": 1}).json()
        self.assertEqual(changed["frozen_criteria"]["threshold_pp"], 5)
        evaluation = self.client.post(url + "/evaluate", json={})
        self.assertEqual(evaluation.status_code, 200, evaluation.text)
        self.assertEqual(evaluation.json()["outcome"], "criterion_not_met")
        self.assertAlmostEqual(evaluation.json()["delta_pp"], 4)
        self.assertEqual(
            self.client.get(self.base + "/knowledge").json()[0]["id"], exp["id"]
        )
        self.client.__exit__(None, None, None)
        self.client = TestClient(app)
        self.client.__enter__()
        self.assertEqual(
            self.client.post("/api/login", json=self.credentials).status_code, 200
        )
        persisted = self.client.get(url).json()
        self.assertEqual(persisted["status"], "completed")
        self.assertEqual(persisted["result"]["outcome"], "criterion_not_met")
        self.assertTrue(
            any(
                e["action"] == "criteria_edited_after_freeze"
                for e in persisted["history"]
            )
        )
        media = self.client.get(
            self.base + "/videos/" + exp["variant_id"] + "/media",
            headers={"Range": "bytes=0-15"},
        )
        self.assertEqual(media.status_code, 206)
        self.assertEqual(len(media.content), 16)

    def test_decode_failure_keeps_draft_and_records_operation(self):
        video = self.upload()
        exp = self.create_experiment(video["id"])
        url = self.base + "/experiments/" + exp["id"]
        job = self.client.post(
            url + "/edit",
            data={"start": "0", "end": "2"},
            files={"file": ("bad.mp4", b"bad-video", "video/mp4")},
        )
        self.assertEqual(job.status_code, 200, job.text)
        failed = self.wait_op(job.json())
        self.assertEqual(failed["status"], "failed")
        current = self.client.get(url).json()
        self.assertEqual(current["status"], "draft")
        self.assertIsNone(current["variant_id"])

    def test_chunked_upload_rejected_before_multipart_parsing(self):
        response = self.client.post(
            self.base + "/videos",
            content=iter([b"--test\r\n"]),
            headers={"Content-Type": "multipart/form-data; boundary=test"},
        )
        self.assertEqual(response.status_code, 411, response.text)
        self.assertEqual(self.client.get(self.base + "/videos").json(), [])

    def test_synthetic_edit_requires_exact_supplied_fixture(self):
        video = self.upload()
        exp = self.create_experiment(video["id"])
        with db.connect() as c:
            import json

            brand = json.loads(
                c.execute(
                    "SELECT payload FROM workspaces WHERE id=?", (self.wid,)
                ).fetchone()[0]
            )
            brand["synthetic"] = True
            c.execute(
                "UPDATE workspaces SET payload=? WHERE id=?", (db.pack(brand), self.wid)
            )
            stored = db.record(c, self.wid, "video", video["id"])
            stored["synthetic"] = True
            db.save(c, self.wid, "video", stored)
        url = self.base + "/experiments/" + exp["id"] + "/edit"
        before = set((db.ROOT / self.wid).glob("*.mp4"))
        missing = self.client.post(
            url,
            data={"start": "0", "end": "2"},
            files={
                "file": ("replacement.mp4", self.replacement.read_bytes(), "video/mp4")
            },
        )
        self.assertEqual(missing.status_code, 409, missing.text)
        self.assertIn("ordinary workspace", missing.json()["detail"])
        self.assertEqual(set((db.ROOT / self.wid).glob("*.mp4")), before)
        fixture = db.ROOT / "demo-coffee" / "replacement.mp4"
        fixture.parent.mkdir()
        fixture.write_bytes(self.replacement.read_bytes())
        different = self.client.post(
            url,
            data={"start": "0", "end": "2"},
            files={"file": ("replacement.mp4", self.video.read_bytes(), "video/mp4")},
        )
        self.assertEqual(different.status_code, 409, different.text)
        self.assertEqual(set((db.ROOT / self.wid).glob("*.mp4")), before)
        self.assertEqual(self.client.get(self.base + "/operations").json(), [])
        self.assertIsNone(
            self.client.get(self.base + "/experiments/" + exp["id"]).json()[
                "variant_id"
            ]
        )
        allowed = self.client.post(
            url,
            data={"start": "0", "end": "2"},
            files={"file": ("renamed.mp4", fixture.read_bytes(), "video/mp4")},
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)
        result = self.wait_op(allowed.json())
        self.assertEqual(result["status"], "completed", result)
        edited = next(
            v
            for v in self.client.get(self.base + "/videos").json()
            if v["id"] == result["result"]["video_id"]
        )
        self.assertTrue(edited["synthetic"])

    def test_synthetic_variant_without_fixture_gets_measured_analysis(self):
        video = self.upload()
        with db.connect() as c:
            row = c.execute(
                "SELECT payload FROM workspaces WHERE id=?", (self.wid,)
            ).fetchone()
            import json

            brand = json.loads(row[0])
            brand["synthetic"] = True
            c.execute(
                "UPDATE workspaces SET payload=? WHERE id=?", (db.pack(brand), self.wid)
            )
        job = self.client.post(
            self.base + "/videos/" + video["id"] + "/analyze", json={"mode": "local"}
        )
        completed = self.wait_op(job.json())
        self.assertEqual(completed["status"], "completed", completed)
        self.assertEqual(completed["result"]["mode"], "local")
        self.assertTrue(completed["result"]["segments"])

    def test_unknown_provider_outcome_halts_followup_requests(self):
        video = self.upload()
        route = self.base + "/videos/" + video["id"] + "/analyze"
        os.environ["CE_OPENAI_APPROVED_BUDGET_USD"] = "1"
        os.environ["OPENAI_API_KEY"] = "fake-never-sent"
        with patch(
            "app.provider.analyze", side_effect=ValueError("unknown timeout")
        ) as provider:
            first = self.wait_op(
                self.client.post(route, json={"mode": "openai"}).json()
            )
            self.assertEqual(first["status"], "failed")
            self.assertTrue(first["budget_halted"])
            second = self.wait_op(
                self.client.post(route, json={"mode": "openai"}).json()
            )
            self.assertEqual(second["status"], "failed")
            self.assertIn("halted", second["error"].lower())
            self.assertEqual(provider.call_count, 1)

    def test_cross_origin_write_rejected(self):
        response = self.client.post(
            "/api/workspaces",
            json={"name": "Blocked"},
            headers={"Origin": "https://outside.invalid"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(self.client.get("/api/workspaces").json()), 1)


if __name__ == "__main__":
    unittest.main()
