"""Auditable CSV validation, observational recommendations and saved scoring.

No inference API is called here. All numeric statements are computed in Python.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from datetime import date, datetime, timezone
from typing import Any

CSV_COLUMNS = [
    "publication_id",
    "video_id",
    "platform",
    "traffic",
    "source",
    "period_start",
    "period_end",
    "views",
    "retention_3s",
    "retention_unit",
]
METRIC_DEFINITION = "Share of video starts still viewing at 3 seconds; fraction in [0, 1]. Views means video starts, not impressions or unique viewers."
CAUSAL_LIMIT = "Observational comparison: audience, distribution and publication timing were not randomized; the difference does not establish a causal effect."


def _day(value: str, label: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{label}: use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label}: invalid calendar date") from None


def _key(row: dict) -> tuple:
    return tuple(
        row.get(k) for k in ("platform", "publication_id", "period_start", "period_end")
    )


def _same(a: dict, b: dict) -> bool:
    return all(a.get(k) == b.get(k) for k in CSV_COLUMNS)


def validate_csv(
    text: str, videos: list[dict], existing: list[dict], now=None
) -> list[dict]:
    """Validate the whole import before returning new rows; duplicates are idempotent.

    Workspaces are scoped by the caller: ``videos`` and ``existing`` must only
    contain rows visible in the selected workspace. No partial import is returned.
    """
    if not isinstance(text, str) or len(text.encode("utf-8")) > 2_000_000:
        raise ValueError("CSV exceeds the 2 MB limit")
    if "\x00" in text:
        raise ValueError("CSV contains a NUL character")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
    try:
        columns = reader.fieldnames
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV: {exc}") from None
    if columns != CSV_COLUMNS:
        raise ValueError("CSV columns, in order, must be: " + ",".join(CSV_COLUMNS))
    video_ids = {str(v["id"]) for v in videos}
    current = now or datetime.now(timezone.utc).date()
    if isinstance(current, datetime):
        current = current.date()
    if isinstance(current, str):
        current = _day(current, "today")
    accepted: list[dict] = []
    seen = {_key(r): r for r in existing}
    all_rows = list(existing)
    count = 0
    try:
        for count, raw in enumerate(reader, 1):
            line = count + 1
            if count > 5000:
                raise ValueError("CSV exceeds 5,000 data rows")
            if None in raw or any(v is None for v in raw.values()):
                raise ValueError(f"Row {line}: wrong number of columns")
            row = {k: v.strip() for k, v in raw.items()}
            for field in ("publication_id", "video_id", "source"):
                value = row[field]
                if not value or len(value) > 200 or any(ord(c) < 32 for c in value):
                    raise ValueError(
                        f"Row {line}: {field} must be 1–200 printable characters"
                    )
                if value.startswith(("=", "+", "-", "@")):
                    raise ValueError(f"Row {line}: formula-like {field} is not allowed")
            if row["video_id"] not in video_ids:
                raise ValueError(f"Row {line}: video does not belong to this workspace")
            if row["platform"] not in {"instagram", "tiktok", "youtube"}:
                raise ValueError(f"Row {line}: unsupported platform")
            if row["traffic"] not in {"organic", "paid"}:
                raise ValueError(f"Row {line}: traffic must be organic or paid")
            if row["retention_unit"] != "fraction":
                raise ValueError(
                    f"Row {line}: retention_unit must be fraction, not percent"
                )
            start, end = (
                _day(row[k], f"Row {line}: {k}") for k in ("period_start", "period_end")
            )
            if start >= end or end > current:
                raise ValueError(f"Row {line}: require start < end <= today (UTC)")
            if row["views"]:
                if not re.fullmatch(r"\d{1,12}", row["views"]):
                    raise ValueError(
                        f"Row {line}: views must be a nonnegative integer or blank"
                    )
                row["views"] = int(row["views"])
            else:
                row["views"] = None
            if row["retention_3s"]:
                try:
                    value = float(row["retention_3s"])
                except ValueError:
                    raise ValueError(
                        f"Row {line}: retention_3s must be numeric or blank"
                    ) from None
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError(
                        f"Row {line}: retention_3s must be a finite fraction in [0, 1]"
                    )
                if row["views"] == 0:
                    raise ValueError(
                        f"Row {line}: retention is undefined when views is zero"
                    )
                row["retention_3s"] = value
            else:
                row["retention_3s"] = None
            key = _key(row)
            if key in seen:
                if not _same(row, seen[key]):
                    raise ValueError(
                        f"Row {line}: conflicting repeat for this publication and period"
                    )
                continue
            # Keep one publication identity stable, including on disjoint windows.
            for old in all_rows:
                if (old["platform"], old["publication_id"]) != (
                    row["platform"],
                    row["publication_id"],
                ):
                    continue
                if any(old.get(k) != row[k] for k in ("video_id", "traffic", "source")):
                    raise ValueError(f"Row {line}: publication metadata changed")
                if (
                    row["period_start"] < old["period_end"]
                    and old["period_start"] < row["period_end"]
                ):
                    raise ValueError(
                        f"Row {line}: overlapping measurement periods for one publication"
                    )
            seen[key] = row
            all_rows.append(row)
            accepted.append(row)
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV: {exc}") from None
    if count == 0:
        raise ValueError("CSV has no data rows")
    return accepted


def _signature(row: dict) -> tuple:
    days = (
        _day(row["period_end"], "period_end")
        - _day(row["period_start"], "period_start")
    ).days
    return (
        row["platform"],
        row["traffic"],
        row["source"],
        days,
        row.get("retention_unit", "fraction"),
    )


def _usable(row: dict) -> bool:
    views, value = row.get("views"), row.get("retention_3s")
    return (
        isinstance(views, int)
        and not isinstance(views, bool)
        and views > 0
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 1
    )


def _source(video: dict) -> dict:
    duration = max(0.0, float(video.get("duration", 0)))
    return {
        "video_id": video["id"],
        "start": 0,
        "end": min(2.0, duration),
        "title": video.get("title", video["id"]),
    }


def recommend(videos: list[dict], metrics: list[dict]) -> list[dict]:
    """One transparent hypothesis per comparable stratum, up to three.

    Means give each video equal weight, avoiding pseudo-replication by view count.
    Repeated publications/windows of a video are excluded, not cherry-picked.
    Two videos per hook group are the minimum for a descriptive pattern; they
    are not a power calculation or evidence of causal significance.
    """
    if not videos:
        return []
    by_id = {str(v["id"]): v for v in videos}
    grouped: dict[tuple, dict[str, list]] = {}
    rows_by_video: dict[str, list] = {}
    for row in metrics:
        if row.get("video_id") in by_id:
            rows_by_video.setdefault(row["video_id"], []).append(row)
    excluded = []
    for vid, rows in rows_by_video.items():
        if len(rows) != 1:
            excluded.append(vid)
            continue
        row = rows[0]
        analysis = by_id[vid].get("analysis") or {}
        category = analysis.get("hook_category", "unknown")
        if (
            category not in {"preparation", "packaging"}
            or not _usable(row)
            or row["views"] < 100
        ):
            continue
        signature = _signature(row)
        grouped.setdefault(signature, {"preparation": [], "packaging": []})[
            category
        ].append((by_id[vid], row))
    candidates = []
    for signature, groups in sorted(grouped.items()):
        prep, pack = groups["preparation"], groups["packaging"]
        if len(prep) < 2 or len(pack) < 2:
            continue
        prep_mean = sum(r["retention_3s"] for _, r in prep) / len(prep)
        pack_mean = sum(r["retention_3s"] for _, r in pack) / len(pack)
        delta = (prep_mean - pack_mean) * 100
        if abs(delta) < 1e-9:
            continue
        preferred = "preparation" if delta > 0 else "packaging"
        contrast = "packaging" if delta > 0 else "preparation"
        records = prep + pack
        baseline = sorted(groups[contrast], key=lambda item: str(item[0]["id"]))[0][0]
        synthetic = any(
            v.get("synthetic")
            or (v.get("analysis") or {}).get("mode") == "synthetic_fixture"
            for v, _ in records
        )
        limitations = [
            CAUSAL_LIMIT,
            "Small convenience sample; equally weighted video means, not pooled viewer-level evidence.",
            "The dates are measurement windows; time since publication and audience overlap are not available.",
            "Hook categories are interpretations or authored fixture labels, not experimentally assigned treatments.",
        ]
        if synthetic:
            limitations.insert(
                0,
                "Synthetic demonstration data: this pattern was authored and is not a real publication finding.",
            )
        if excluded:
            limitations.append(
                f"Excluded {len(excluded)} videos with multiple publication/window records to avoid cherry-picking or double counting."
            )
        key = repr(signature) + ":" + ",".join(sorted(v["id"] for v, _ in records))
        candidates.append(
            {
                "id": hashlib.sha256(key.encode()).hexdigest()[:16],
                "title": f"Test a {preferred} opening",
                "kind": "observational",
                "generator": "rules-v1",
                "baseline_id": baseline["id"],
                "observation": f"In this compatible stratum, {len(prep)} preparation-opening videos averaged {prep_mean * 100:.1f}% retention at 3s; {len(pack)} packaging-opening videos averaged {pack_mean * 100:.1f}%. Preparation minus packaging: {delta:+.1f} percentage points.",
                "hypothesis": f"Replacing a {contrast} opening with {preferred} in the first two seconds may improve 3-second retention.",
                "change": f"Replace only seconds 0–2 with a {preferred} opening.",
                "preserve": [
                    "Video after second 2",
                    "Original audio",
                    "Offer and call to action",
                    "Total duration and aspect ratio",
                ],
                "metric": "retention_3s",
                "metric_definition": METRIC_DEFINITION,
                "threshold_pp": 5,
                "min_views": 100,
                "window_days": 7,
                "evaluation_rule": "Compare compatible 7-day windows with at least 100 starts per version; require a +5 percentage-point difference. Report only an observed criterion outcome.",
                "limitations": limitations,
                "sources": [
                    _source(v)
                    for v, _ in sorted(records, key=lambda item: str(item[0]["id"]))
                ],
                "stats": {
                    "preparation_n": len(prep),
                    "packaging_n": len(pack),
                    "preparation_mean": prep_mean,
                    "packaging_mean": pack_mean,
                    "delta_pp": delta,
                    "platform": signature[0],
                    "traffic": signature[1],
                    "source": signature[2],
                    "period_days": signature[3],
                    "aggregation": "unweighted mean across videos",
                    "synthetic": synthetic,
                },
            }
        )
    if candidates:
        # Deterministic stratum order, never rank by the largest observed uplift.
        return candidates[:3]
    baseline = sorted(videos, key=lambda v: str(v["id"]))[0]
    return [
        {
            "id": "exploratory-" + str(baseline["id"]),
            "title": "Explore a different opening",
            "kind": "exploratory",
            "generator": "rules-v1",
            "baseline_id": baseline["id"],
            "observation": "Insufficient comparable labeled videos and metrics to identify a pattern. No successful pattern has been established.",
            "hypothesis": "Changing the first two seconds to show the product in use may improve 3-second retention; this remains an untested idea.",
            "change": "Replace only seconds 0–2 with a clear product-in-use shot.",
            "preserve": [
                "Video after second 2",
                "Original audio",
                "Offer and call to action",
                "Total duration and aspect ratio",
            ],
            "metric": "retention_3s",
            "metric_definition": METRIC_DEFINITION,
            "threshold_pp": 5,
            "min_views": 100,
            "window_days": 7,
            "evaluation_rule": "Collect compatible 7-day windows with at least 100 starts per version. Compare the observed difference against +5 percentage points.",
            "limitations": [
                "Exploratory proposal, not a data-supported winning pattern.",
                CAUSAL_LIMIT,
                "Need at least two videos per recognized opening category with one compatible publication/window each for a descriptive comparison.",
            ],
            "sources": [_source(baseline)],
            "stats": {
                "eligible_pattern_count": 0,
                "synthetic": bool(baseline.get("synthetic")),
            },
        }
    ]


def evaluate(
    experiment: dict, baseline_metrics: list[dict], variant_metrics: list[dict]
) -> dict:
    """Evaluate fixed criteria; missing or incomparable data is a first-class result."""
    frozen = experiment.get("frozen_criteria")
    criteria = (
        dict(frozen)
        if isinstance(frozen, dict)
        else {
            k: experiment.get(k)
            for k in ("metric", "threshold_pp", "min_views", "window_days", "revision")
        }
    )
    limits = [
        CAUSAL_LIMIT,
        "No randomized assignment or population uncertainty estimate is available.",
    ]
    result = {
        "outcome": "insufficient_data",
        "summary": "Insufficient comparable results.",
        "baseline": None,
        "variant": None,
        "delta_pp": None,
        "limitations": limits,
        "criteria": criteria,
    }
    if criteria.get("metric") != "retention_3s":
        result["summary"] = "Unsupported primary metric."
        return result
    try:
        threshold = float(criteria["threshold_pp"])
        min_views = int(criteria["min_views"])
        days = int(criteria["window_days"])
        if (
            not math.isfinite(threshold)
            or not 0 <= threshold <= 100
            or min_views < 1
            or days < 1
        ):
            raise ValueError()
    except (KeyError, TypeError, ValueError, OverflowError):
        result["summary"] = "Invalid or missing saved criteria."
        return result
    if len(baseline_metrics) != 1 or len(variant_metrics) != 1:
        result["summary"] = (
            "Require exactly one publication/window per version. Missing or multiple records cannot be selected after seeing results."
        )
        return result
    base, variant = baseline_metrics[0], variant_metrics[0]
    result["baseline"], result["variant"] = dict(base), dict(variant)
    if base.get("video_id") != experiment.get("baseline_id") or variant.get(
        "video_id"
    ) != experiment.get("variant_id"):
        result["summary"] = (
            "Metrics do not reference the experiment's baseline and variant."
        )
        return result
    if base.get("publication_id") == variant.get("publication_id") and base.get(
        "platform"
    ) == variant.get("platform"):
        result["summary"] = "Baseline and variant require distinct publications."
        return result
    if not _usable(base) or not _usable(variant):
        result["summary"] = (
            "Missing or undefined retention or view count; absent values are not zero."
        )
        return result
    try:
        bs, vs = _signature(base), _signature(variant)
    except (ValueError, KeyError, TypeError):
        result["summary"] = "Invalid metric provenance or measurement dates."
        return result
    if bs != vs or bs[-1] != "fraction":
        result["summary"] = (
            "Platform, organic/paid traffic, source, units and observation-window length must match."
        )
        return result
    if bs[3] != days:
        result["summary"] = (
            f"Both observation windows must match the saved {days}-day duration."
        )
        return result
    if min(base["views"], variant["views"]) < min_views:
        result["summary"] = (
            f"At least {min_views} video starts are required for each version."
        )
        return result
    delta = (variant["retention_3s"] - base["retention_3s"]) * 100
    result["delta_pp"] = delta
    met = delta + 1e-9 >= threshold
    result["outcome"] = "observed_improvement" if met else "criterion_not_met"
    result["summary"] = (
        f"Observed retention changed from {base['retention_3s']*100:.1f}% to {variant['retention_3s']*100:.1f}% ({delta:+.1f} percentage points). The saved +{threshold:g} pp criterion {'was met' if met else 'was not met'}. This does not establish causation."
    )
    return result


def gen_brief(experiment: dict) -> dict:
    """A deterministic production brief; not generated footage or a model response."""
    return {
        "status": "generation_brief_only",
        "generator": "template-v1",
        "provider": None,
        "interval": {
            "start": experiment.get("edit_start", 0),
            "end": experiment.get("edit_end", 2),
        },
        "instruction": f"Create an alternate segment of {experiment.get('edit_end',2)-experiment.get('edit_start',0):g} seconds. Requested change: {experiment.get('change', 'Show the product in use')}. Hypothesis: {experiment.get('hypothesis', '')}",
        "preserve": experiment.get(
            "preserve",
            [
                "Remainder of the source video",
                "Original audio",
                "Offer and call to action",
                "Total duration",
            ],
        ),
        "technical": f"Match the source aspect ratio. Supply at least {experiment.get('edit_end',2)-experiment.get('edit_start',0):g} seconds at 24 fps. Replacement audio is ignored; the original soundtrack remains unchanged.",
        "limitations": [
            "This is a preparation brief. No video-generation provider was called.",
            "Uploaded alternative footage is not automatically classified as AI-generated.",
            "The assembled version and its measured edit report are separate artifacts.",
        ],
    }
