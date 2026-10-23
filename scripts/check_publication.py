"""Reject obvious credentials/private files before publishing reachable Git history.

This is a bounded publication guard, not a complete secret scanner or security audit.
It never reads untracked files or prints matched secret values.
"""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(rb'(?:sk-(?:proj-)?[A-Za-z0-9_-]{40,}|AIza[A-Za-z0-9_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def main():
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    forbidden = [p for p in files if p and (
        p.startswith(('data/', '.venv/', 'artifacts/private'))
        or Path(p).name.startswith('.env')
        or Path(p).suffix in {'.pem', '.key', '.sqlite', '.sqlite3', '.db'}
    )]
    rows = subprocess.check_output(['git', 'rev-list', '--objects', 'HEAD'], cwd=ROOT, text=True).splitlines()
    matched = []
    blobs = 0
    with subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
        for row in rows:
            oid, _, name = row.partition(' ')
            proc.stdin.write((oid + '\n').encode())
            proc.stdin.flush()
            header = proc.stdout.readline().decode().split()
            body = proc.stdout.read(int(header[2]))
            proc.stdout.read(1)
            if header[1] != 'blob':
                continue
            blobs += 1
            if name.startswith(('data/', '.venv/', 'artifacts/private')) or Path(name).name.startswith('.env'):
                forbidden.append(name)
            if SECRET.search(body):
                matched.append({'object': oid, 'path': name})
        proc.stdin.close()
        proc.wait()
    report = {'status': 'blocked' if forbidden or matched else 'passed',
              'tracked_files': len([p for p in files if p]), 'history_blobs_checked': blobs,
              'forbidden_paths': sorted(set(forbidden)), 'credential_pattern_matches': matched,
              'scope': 'Git-tracked files and reachable history only; no secret values printed.'}
    print(json.dumps(report, indent=2))
    return 1 if forbidden or matched else 0


if __name__ == '__main__':
    raise SystemExit(main())
