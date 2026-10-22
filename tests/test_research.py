import csv
import io
import unittest
from copy import deepcopy

from app.research import CSV_COLUMNS, evaluate, gen_brief, recommend, validate_csv


def metric(vid="a", pub="p1", value=0.4, **kw):
    row = dict(
        publication_id=pub,
        video_id=vid,
        platform="instagram",
        traffic="organic",
        source="manual-export-v1",
        period_start="2026-01-01",
        period_end="2026-01-08",
        views=200,
        retention_3s=value,
        retention_unit="fraction",
    )
    row.update(kw)
    return row


def csv_text(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


class CSVTests(unittest.TestCase):
    def parse(self, rows, existing=()):
        return validate_csv(
            csv_text(rows), [{"id": "a"}, {"id": "b"}], list(existing), now="2026-01-31"
        )

    def test_null_preserved(self):
        row = self.parse([metric(views="", value="")])[0]
        self.assertIsNone(row["views"])
        self.assertIsNone(row["retention_3s"])

    def test_repeat_is_idempotent(self):
        row = metric()
        self.assertEqual(self.parse([row, row]), [row])
        self.assertEqual(self.parse([row], existing=[row]), [])

    def test_conflicting_repeat_is_atomic(self):
        rows = [metric("b", "new"), metric(value=0.5)]
        with self.assertRaisesRegex(ValueError, "conflicting"):
            self.parse(rows, existing=[metric()])

    def test_overlap_and_publication_reassignment_rejected(self):
        for changed in [
            dict(period_start="2026-01-05", period_end="2026-01-12"),
            dict(video_id="b", period_start="2026-01-09", period_end="2026-01-16"),
        ]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.parse([metric(**changed)], existing=[metric()])

    def test_foreign_video_rejected(self):
        with self.assertRaisesRegex(ValueError, "workspace"):
            self.parse([metric("foreign")])

    def test_invalid_numbers_units_dates(self):
        for changed in [
            dict(retention_3s="nan"),
            dict(retention_3s="inf"),
            dict(retention_3s="40"),
            dict(views="1.5"),
            dict(views="-1"),
            dict(views=0),
            dict(retention_unit="percent"),
            dict(period_end="2026-02-01"),
            dict(period_start="2026-01-09"),
            dict(period_start="2026-1-01"),
            dict(source="=cmd()"),
        ]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.parse([metric(**changed)])

    def test_header_and_missing_columns(self):
        for text in [
            "video_id,views\na,100\n",
            csv_text([metric()]).replace("retention_unit", "retention_3s"),
            ",".join(CSV_COLUMNS) + "\na,b\n",
        ]:
            with self.assertRaises(ValueError):
                validate_csv(text, [{"id": "a"}], [], now="2026-01-31")


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.videos = [
            dict(
                id=str(i),
                title=f"Video {i}",
                duration=8,
                synthetic=True,
                analysis={
                    "hook_category": "preparation" if i < 2 else "packaging",
                    "mode": "synthetic_fixture",
                },
            )
            for i in range(4)
        ]
        self.metrics = [
            metric(str(i), str(i), v) for i, v in enumerate([0.6, 0.7, 0.4, 0.5])
        ]

    def test_stats_sources_and_limits(self):
        rec = recommend(self.videos, self.metrics)[0]
        self.assertEqual(rec["kind"], "observational")
        self.assertAlmostEqual(rec["stats"]["delta_pp"], 20)
        self.assertEqual(len(rec["sources"]), 4)
        self.assertTrue(any("Synthetic" in s for s in rec["limitations"]))
        self.assertTrue(any("causal" in s for s in rec["limitations"]))
        self.assertEqual(rec["stats"]["aggregation"], "unweighted mean across videos")

    def test_do_not_mix_paid_or_platform_or_source(self):
        for key, value in [
            ("traffic", "paid"),
            ("platform", "tiktok"),
            ("source", "different"),
            ("period_end", "2026-01-09"),
        ]:
            rows = deepcopy(self.metrics)
            for row in rows[:2]:
                row[key] = value
            with self.subTest(key=key):
                self.assertEqual(recommend(self.videos, rows)[0]["kind"], "exploratory")

    def test_unknown_semantics_or_no_data_is_exploratory(self):
        self.assertEqual(recommend(self.videos, [])[0]["kind"], "exploratory")
        for v in self.videos:
            v["analysis"] = None
        self.assertEqual(recommend(self.videos, self.metrics)[0]["kind"], "exploratory")
        self.assertEqual(recommend([], []), [])

    def test_no_selecting_best_window(self):
        rows = self.metrics + [metric("0", "repeat", 0.99)]
        self.assertEqual(recommend(self.videos, rows)[0]["kind"], "exploratory")


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.exp = {
            "baseline_id": "a",
            "variant_id": "b",
            "metric": "retention_3s",
            "threshold_pp": 5,
            "min_views": 100,
            "window_days": 7,
            "revision": 1,
        }
        self.base = [metric()]
        self.variant = [metric("b", "p2", 0.5)]

    def test_observed_success_and_failure(self):
        result = evaluate(self.exp, self.base, self.variant)
        self.assertEqual(result["outcome"], "observed_improvement")
        self.assertAlmostEqual(result["delta_pp"], 10)
        self.assertIn("does not establish causation", result["summary"])
        self.variant[0]["retention_3s"] = 0.42
        self.assertEqual(
            evaluate(self.exp, self.base, self.variant)["outcome"], "criterion_not_met"
        )

    def test_frozen_criteria_win_over_edited_fields(self):
        self.exp["frozen_criteria"] = {**self.exp, "threshold_pp": 20}
        self.exp["threshold_pp"] = 0
        self.assertEqual(
            evaluate(self.exp, self.base, self.variant)["outcome"], "criterion_not_met"
        )

    def test_insufficient_is_first_class(self):
        for rows in [
            [],
            self.variant * 2,
            [metric("b", "p2", None)],
            [metric("b", "p2", 0.5, views=99)],
            [metric("b", "p2", 0.5, traffic="paid")],
            [metric("b", "p2", 0.5, period_end="2026-01-15")],
            [metric("a", "p2", 0.5)],
        ]:
            with self.subTest(rows=rows):
                self.assertEqual(
                    evaluate(self.exp, self.base, rows)["outcome"], "insufficient_data"
                )

    def test_zero_is_not_missing_retention(self):
        self.base[0]["retention_3s"] = 0
        self.assertEqual(
            evaluate(self.exp, self.base, self.variant)["outcome"],
            "observed_improvement",
        )

    def test_generation_brief_does_not_claim_generation(self):
        self.assertEqual(gen_brief(self.exp)["status"], "generation_brief_only")
        self.assertIsNone(gen_brief(self.exp)["provider"])


if __name__ == "__main__":
    unittest.main()
