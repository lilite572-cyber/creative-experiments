#!/usr/bin/env python3
"""Check both frozen pilots, then explicitly execute within their allocated caps."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-4.1-mini-2025-04-14"


def load_private_key(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or not 20 <= info.st_size <= 1024):
            raise ValueError("Key must be an owned regular 0600 file")
        with os.fdopen(descriptor, "r", closefd=False) as handle:
            value = handle.read(1025).strip()
        if not value.startswith("sk-") or any(ch.isspace() for ch in value):
            raise ValueError("Invalid key file format")
        return value
    finally:
        os.close(descriptor)


def provider_check(key: str) -> dict:
    """Model metadata only: never sends a video or inference request."""
    try:
        with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
            response = client.get(
                f"https://api.openai.com/v1/models/{MODEL}",
                headers={"Authorization": "Bearer " + key},
            )
            available = response.status_code == 200 and response.json().get("id") == MODEL
            return {"available": available, "http_status": response.status_code,
                    "model": MODEL, "inference_requests": 0}
    except (httpx.HTTPError, ValueError, AttributeError):
        return {"available": False, "error": "connection_or_metadata_failure",
                "model": MODEL, "inference_requests": 0}


def jobs(briefguard_root: Path) -> list[dict]:
    bg_python = briefguard_root / ".venv-pilot/bin/python"
    if not bg_python.is_file():
        bg_python = briefguard_root / ".venv/bin/python"
    bg_command = [str(bg_python), str(briefguard_root / "scripts/run_pilot_guarded.py"),
                  "--directory", str(briefguard_root / "results/private-vlm-pilot-v2")]
    ce_command = [sys.executable, str(ROOT / "scripts/run_live_pilot.py"),
                  str(ROOT / "data/private/ce-live-pilot-three-sources")]
    return [
        {"name": "BriefGuard", "cwd": briefguard_root,
         "check": bg_command + ["--check-only"],
         "execute": bg_command + ["--approve-openai-gpt41mini-usd050"]},
        {"name": "Creative Experiments", "cwd": ROOT,
         "check": ce_command + ["--check-only"], "execute": ce_command},
    ]


def preflight(planned: list[dict]) -> dict:
    checks = []
    for job in planned:
        try:
            process = subprocess.run(job["check"], cwd=job["cwd"], capture_output=True,
                                     text=True, timeout=90, check=False)
            # These fixed readiness commands contain no credentials and make no HTTP calls.
            detail = (process.stdout or process.stderr).strip()[:3000]
            checks.append({"project": job["name"], "ready": process.returncode == 0,
                           "detail": detail})
        except (OSError, subprocess.TimeoutExpired):
            checks.append({"project": job["name"], "ready": False,
                           "detail": "Local readiness command unavailable or timed out"})
    return {"ready": all(item["ready"] for item in checks), "checks": checks,
            "allocated_local_limits_usd": {"BriefGuard": 0.5, "Creative Experiments": 5.0},
            "user_total_ceiling_usd": 8.0, "unallocated_usd": 2.5}


def execute(planned: list[dict], key: str) -> int:
    environment = dict(os.environ, OPENAI_API_KEY=key)
    for job in planned:
        print(f"Running {job['name']} with its persistent ledger.", flush=True)
        # No key in arguments or printed environment. Never stream arbitrary child output.
        process = subprocess.run(job["execute"], cwd=job["cwd"], env=environment,
                                 capture_output=True, text=True, check=False)
        safe_output = (process.stdout + process.stderr).replace(key, "[redacted]")
        print(safe_output[-12000:], flush=True)
        if process.returncode:
            print("Stopped. Preserve both ledgers; inspect the saved failure before retrying.")
            return 2
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--briefguard-root", type=Path, default=ROOT.parent / "briefguard")
    parser.add_argument("--check-provider", action="store_true",
                        help="Check model access without inference; reads the private local key")
    parser.add_argument("--execute", action="store_true",
                        help="Execute already-authorized pilots only after both readiness checks pass")
    args = parser.parse_args(argv)
    planned = jobs(args.briefguard_root.resolve())
    status = preflight(planned)
    key_path = ROOT / "data/private/openai_api_key"
    status["key_file_present"] = key_path.is_file()
    print(json.dumps(status, indent=2, ensure_ascii=False), flush=True)
    if args.execute and not status["ready"]:
        print("Not ready: complete the real human labels and source confirmations. No inference sent.")
        return 2
    if not args.execute and not args.check_provider:
        return 0 if status["ready"] else 2
    try:
        key = load_private_key(key_path)
    except (OSError, ValueError, UnicodeError):
        print("Private key unavailable or unsafe file permissions. No inference sent.")
        return 2
    model = provider_check(key)
    print(json.dumps(model, indent=2))
    if not model["available"]:
        print("Model access not confirmed; no inference sent. A connection failure is not proof of an invalid key.")
        return 2
    return execute(planned, key) if args.execute else 0


if __name__ == "__main__":
    raise SystemExit(main())
