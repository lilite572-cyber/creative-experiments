#!/usr/bin/env python3
"""Freeze an owned/licensed MP4 pilot and unsent visual requests, entirely offline."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.media import extract_frames, probe
from app.provider import MODEL, PROMPT_VERSION, prepare_request

COLUMNS = ["source_id", "path", "source_url", "credit", "rights_url", "rights_note", "distribution_allowed"]
REVIEW_COLUMNS = ["source_id", "frame_index", "timestamp_seconds", "hook_category", "observation_kind", "visible_text", "supported_description", "reviewer", "notes"]
FROZEN_CODE = ["app/media.py", "app/provider.py", "scripts/prepare_live_pilot.py", "configs/live_pilot_v1.json", "docs/live_pilot.md"]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _url(value: str, label: str) -> None:
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError(f"{label} must be an https URL without embedded credentials")
    if len(value) > 2000 or any(ord(ch) < 32 for ch in value):
        raise ValueError(f"{label} is invalid or too long")
    if parts.query or parts.fragment:
        raise ValueError(f"{label} must be a stable source page, without query strings or fragments")


def read_manifest(manifest: Path, media_root: Path, config: dict) -> list[dict]:
    media_root = media_root.resolve(strict=True)
    if not media_root.is_dir():
        raise ValueError("Media root must be a directory")
    if manifest.stat().st_size > 128 * 1024:
        raise ValueError("Manifest exceeds 128 KiB")
    text = manifest.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), strict=True)
    if reader.fieldnames != COLUMNS:
        raise ValueError("Manifest columns must be exactly: " + ",".join(COLUMNS))
    rows, seen_ids, seen_paths, seen_hashes = [], set(), set(), set()
    total = 0
    try:
        for line, raw in enumerate(reader, 2):
            if len(rows) >= config["max_independent_sources"]:
                raise ValueError("The pilot accepts at most 20 independent sources")
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError(f"Manifest row {line}: wrong number of fields")
            row = {key: value.strip() for key, value in raw.items()}
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", row["source_id"]):
                raise ValueError(f"Manifest row {line}: invalid source_id")
            for key in ("credit", "rights_note"):
                if not row[key] or len(row[key]) > 2000 or any(ord(ch) < 32 for ch in row[key]):
                    raise ValueError(f"Manifest row {line}: {key} must be nonempty printable text")
            _url(row["source_url"], "source_url")
            _url(row["rights_url"], "rights_url")
            if row["distribution_allowed"] not in {"true", "false"}:
                raise ValueError("distribution_allowed must be explicitly true or false")
            relative = Path(row["path"])
            if relative.is_absolute() or ".." in relative.parts or "\\" in row["path"] or not row["path"]:
                raise ValueError("Media paths must be relative to media-root, without parent traversal")
            resolved = (media_root / relative).resolve(strict=True)
            if not resolved.is_relative_to(media_root) or not resolved.is_file():
                raise ValueError("Media path escapes media-root or is not a regular file")
            if resolved.suffix.lower() != ".mp4" or not 12 <= resolved.stat().st_size <= 100 * 1024 * 1024:
                raise ValueError("Each source must be an MP4 of at most 100 MiB")
            total += resolved.stat().st_size
            if total > config["max_total_source_bytes"]:
                raise ValueError("Pilot sources exceed the combined 500 MiB limit")
            digest = sha(resolved)
            if row["source_id"] in seen_ids or resolved in seen_paths or digest in seen_hashes:
                raise ValueError("Repeated source ID, path or identical source bytes cannot count as independent sources")
            seen_ids.add(row["source_id"]); seen_paths.add(resolved); seen_hashes.add(digest)
            rows.append({**row, "resolved_path": resolved, "source_sha256": digest})
    except csv.Error as exc:
        raise ValueError(f"Malformed source manifest: {exc}") from None
    if not rows:
        raise ValueError("Source manifest is empty; add lawful independent source MP4 files before preparation")
    return rows


def _review_page(sources: list[dict]) -> str:
    sections = []
    for source in sources:
        sid = html.escape(source["source_id"])
        pictures = "".join(f'<figure><img loading="lazy" src="{html.escape(frame["path"])}" alt="Source {sid}, frame {frame["index"]}"><figcaption>Frame {frame["index"]} · {frame["time"]:.3f} s</figcaption></figure>' for frame in source["frames"])
        sections.append(f'<section><h2>{sid}</h2><p>Credit: {html.escape(source["credit"])}</p><p><a href="{html.escape(source["source_url"])}" rel="noreferrer">Original source</a> · <a href="{html.escape(source["rights_url"])}" rel="noreferrer">Rights reference</a></p><video controls preload="metadata" src="{html.escape(source["media_path"])}"></video><div class="frames">{pictures}</div></section>')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Creative Experiments — source review</title><style>body{max-width:1100px;margin:32px auto;padding:0 20px;font:15px/1.5 system-ui;color:#25332f;background:#f5f5f0}section{background:white;border:1px solid #ddd;padding:24px;margin:24px 0}video{width:100%;max-height:460px}.frames{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}figure{margin:0}img{width:100%;height:160px;object-fit:contain;background:#eee}figcaption{font-size:12px}a{color:#195d4e}</style><h1>Human source review</h1><p>Review the full videos and sampled frames before seeing model answers. No model predictions are included on this page. This is local practical blinding, not an independent expert review.</p><p>Fill <a href="human_review.csv" download>human_review.csv</a> with your own observations. Leave uncertain labels blank and explain why in notes. Use hook categories preparation, packaging, other or unknown; use observation kinds hook, scene, product, text or cta. Do not infer speech from a frame. Record only what is visibly supported, the visible text when readable, and your reviewer name.</p><p>Source rights and recording independence require your verification. Distribution flags in this packet are declarations, not permission granted by this tool. Keep the packet private.</p>''' + "".join(sections) + "</html>"


def prepare(manifest: Path, media_root: Path, output: Path) -> dict:
    code_hashes = {name: sha(ROOT / name) for name in FROZEN_CODE}
    manifest_hash = sha(Path(manifest))
    config = json.loads((ROOT / "configs/live_pilot_v1.json").read_text())
    if config["model"] != MODEL or config["prompt_version"] != PROMPT_VERSION:
        raise ValueError("Pinned provider model/prompt differs from this protocol; prepare a separately versioned protocol")
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists; existing freezes are never overwritten")
    rows = read_manifest(Path(manifest), Path(media_root), config)
    output.parent.mkdir(parents=True, exist_ok=True)
    output = output.absolute()
    with tempfile.TemporaryDirectory(prefix=".prepare-pilot-", dir=output.parent) as temporary:
        staged = Path(temporary) / "packet"
        staged.mkdir()
        sources, planned, labels = [], [], []
        for row in rows:
            source_dir = staged / "sources" / row["source_id"]
            source_dir.mkdir(parents=True)
            media = source_dir / "source.mp4"
            shutil.copyfile(row["resolved_path"], media)
            if sha(media) != row["source_sha256"]:
                raise ValueError("Source changed during preparation; no packet was published")
            metadata = probe(media)
            frames = extract_frames(media, source_dir / "frames")
            if len(frames) != config["frames_per_video"]:
                raise ValueError("Each source must contain at least eight distinct sampled frames")
            request, audit = prepare_request(metadata, frames)
            if request["max_output_tokens"] != config["max_output_tokens"]:
                raise ValueError("Provider output cap differs from the frozen pilot")
            request_path = source_dir / "request.unsent.json"
            request_path.write_text(json.dumps(request, indent=2) + "\n")
            frame_records = [{"path": str(frame["path"].relative_to(staged)), "time": frame["time"], "index": frame["index"], "sha256": sha(frame["path"])} for frame in frames]
            source = {key: row[key] for key in COLUMNS if key != "path"}
            source.update({"original_relative_path": row["path"], "source_sha256": row["source_sha256"], "media_path": str(media.relative_to(staged)), "measured": metadata, "frames": frame_records, "request_path": str(request_path.relative_to(staged)), "request_sha256": sha(request_path), "request_audit": audit})
            sources.append(source)
            for repetition in range(1, config["analysis_repetitions_per_source"] + 1):
                planned.append({"operation_id": f'{row["source_id"]}-analysis-{repetition}', "source_id": row["source_id"], "repetition": repetition, "kind": "visual_analysis", "request_path": source["request_path"], "request_sha256": source["request_sha256"], "status": "prepared_not_executed", "reservation_usd": config["reservation_usd_per_attempt"]})
            labels.extend({"source_id": row["source_id"], "frame_index": frame["index"], "timestamp_seconds": f'{frame["time"]:.6f}'} for frame in frames)
        with (staged / "human_review.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS); writer.writeheader(); writer.writerows(labels)
        (staged / "review.html").write_text(_review_page(sources))
        shutil.copyfile(manifest, staged / "sources_manifest.csv")
        if sha(staged / "sources_manifest.csv") != manifest_hash or any(sha(ROOT / name) != digest for name, digest in code_hashes.items()):
            raise ValueError("Manifest, protocol or source code changed during preparation; no packet was published")
        sorted_ids = sorted(source["source_id"] for source in sources)
        hypothesis_groups = [sorted_ids[position::3] for position in range(3)]
        hypothesis_plan = [{"operation_id": f"hypothesis-group-{i+1}-repeat-{repetition}", "source_ids": group, "repetition": repetition, "kind": "exploratory_hypothesis", "status": "inputs_pending_real_analysis", "reservation_usd": config["reservation_usd_per_attempt"]} for i, group in enumerate(hypothesis_groups) if group for repetition in (1, 2)]
        (staged / "source_confirmation.json").write_text(json.dumps({"reviewer": "", "sources": [{"source_id": row["source_id"], "independent_original_recording_confirmed": None, "lawful_api_analysis_confirmed": None, "rights_reference_reviewed": None, "notes": ""} for row in rows]}, indent=2) + "\n")
        freeze = {"protocol_id": config["protocol_id"], "prepared_at_utc": datetime.now(timezone.utc).isoformat(), "status": "prepared_not_executed_human_review_pending", "config": config, "manifest_sha256": manifest_hash, "code_sha256": code_hashes, "sources": sources, "analysis_operations": planned, "hypothesis_operations": hypothesis_plan, "reserved_hypothesis_slots": config["maximum_hypothesis_attempts"], "reserved_diagnostic_recovery_slots": config["diagnostic_recovery_attempts"], "external_api_calls": 0, "api_cost_usd": 0, "actual_independent_sources": "requires human provenance confirmation", "source_count": len(sources), "human_review_template_sha256": sha(staged / "human_review.csv"), "limitations": ["No inference was executed. No human labels were filled.", "Distinct files and IDs do not prove independent recordings.", "Two repetitions of a source are repeated observations, not independent samples.", "Only visual frames are prepared; no transcription or video generation.", "Hypothesis inputs require observed pilot outcomes and provenance review; six slots are reserved but no claims or requests fabricated."]}
        (staged / "freeze.json").write_text(json.dumps(freeze, indent=2) + "\n")
        staged.rename(output)
    return {"status": "prepared_not_executed", "output": str(output), "sources": len(rows), "analysis_operations": len(planned), "frames": len(labels), "external_api_calls": 0, "api_cost_usd": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--media-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.manifest, args.media_root, args.out)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Preparation not completed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
