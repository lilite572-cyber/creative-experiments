"""Run offline acceptance checks and retain command output plus source hashes."""

from __future__ import annotations

import hashlib
import argparse
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "verification"


def main() -> int:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=OUT)
    OUT = parser.parse_args().output_dir.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    commands = [
        ("tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("dependencies", [sys.executable, "-m", "pip", "check"]),
        ("recommendations", [sys.executable, "scripts/evaluate_recommendations.py"]),
    ]
    if shutil.which("node"):
        commands.append(("javascript", ["node", "--check", "web/app.js"]))
    records = []
    for name, command in commands:
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, timeout=180
        )
        suffix = "json" if name == "recommendations" else "txt"
        output = OUT / f"{name}.{suffix}"
        output.write_text(
            result.stdout + ("" if name == "recommendations" else result.stderr)
        )
        records.append(
            {
                "check": name,
                "command": command,
                "exit_code": result.returncode,
                "output": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
                "stderr": result.stderr if name == "recommendations" else None,
            }
        )
        print(f"{name}: {'PASS' if result.returncode == 0 else 'FAIL'}")
    files = sorted(
        p
        for directory in ("app", "web", "tests", "scripts", "fixtures")
        for p in (ROOT / directory).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    files += [ROOT / "requirements.txt", ROOT / "requirements.lock"]
    manifest = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "live_api_calls": 0,
        "checks": records,
        "javascript_check_skipped": not bool(shutil.which("node")),
        "sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        },
    }
    (OUT / "verification.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return int(any(record["exit_code"] for record in records))


if __name__ == "__main__":
    raise SystemExit(main())
