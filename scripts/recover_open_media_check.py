#!/usr/bin/env python3
"""Explicit one-shot recovery of the reviewed failure; preserve its unknown charge."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import run_open_media_check as original
from provider_diagnostics import DiagnosticTransport, safe_text

guard = original.guard
PLAN = ROOT / 'data/private/open-media-recovery-v1/plan.json'
EXPECTED_LEDGER = 'b2e69607c5882f6305c46b0e14617f6fbed6a48187d6f1f8949514b7820d16b3'
FILES = ['ledger.json', 'origin.json', 'attempt-analysis.json', 'summary.json']
RUNTIME = ['scripts/recover_open_media_check.py', 'scripts/provider_diagnostics.py',
           'docs/open_media_recovery_v1.md']


def prepare():
    original.check_packet()
    root = guard.LEDGER_ROOT
    if guard._sha(root / 'ledger.json') != EXPECTED_LEDGER:
        raise ValueError('Not the reviewed failed ledger; no recovery prepared')
    if PLAN.exists():
        raise ValueError('Recovery plan already exists; do not overwrite')
    PLAN.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    plan = {'protocol': 'open-media-recovery-v1', 'prior_files': {
                name: guard._sha(root / name) for name in FILES},
            'source_freeze_sha256': guard._sha(original.PACKET / 'freeze.json'),
            'runtime': {name: guard._sha(ROOT / name) for name in RUNTIME},
            'additional_max_attempts': 2, 'retained_unknown_reservation_usd': .1,
            'total_reservation_ceiling_usd': .3, 'automatic_retries': 0}
    guard._write(PLAN, plan)
    return {'status': 'prepared', 'inference_requests': 0, 'total_reservation_ceiling_usd': .3}


def check_plan():
    freeze, frames = original.check_packet()
    plan = guard._json(PLAN)
    if (plan.get('protocol') != 'open-media-recovery-v1' or set(plan['runtime']) != set(RUNTIME)
            or set(plan['prior_files']) != set(FILES)
            or plan.get('additional_max_attempts') != 2 or plan.get('automatic_retries') != 0
            or plan.get('total_reservation_ceiling_usd') != .3
            or plan.get('retained_unknown_reservation_usd') != .1):
        raise ValueError('Unexpected recovery plan')
    for name, digest in plan['runtime'].items():
        if guard._sha(ROOT / name) != digest:
            raise ValueError('Recovery runtime/protocol changed')
    if guard._sha(original.PACKET / 'freeze.json') != plan['source_freeze_sha256']:
        raise ValueError('Original input freeze changed')
    return plan, freeze, frames


def validate_prior(plan):
    root = guard.LEDGER_ROOT
    if plan['prior_files']['ledger.json'] != EXPECTED_LEDGER:
        raise ValueError('Recovery is not bound to reviewed failure')
    for name, digest in plan['prior_files'].items():
        if guard._sha(guard._local(root, name)) != digest:
            raise ValueError('Prior ledger or evidence changed; recovery/replay refused')
    ledger = guard._json(root / 'ledger.json')
    attempts = ledger.get('attempts', [])
    if (len(attempts) != 1 or attempts[0]['status'] != 'unknown'
            or attempts[0]['operation_id'] != 'analysis'
            or ledger.get('reserved_cents') != 10 or ledger.get('limit_cents') != 500
            or ledger.get('halted') is not True):
        raise ValueError('Unexpected failed-run accounting')
    return ledger


def execute(*, key=None, availability=None, transport_factory=DiagnosticTransport):
    plan, freeze, frames = check_plan()
    root = guard.LEDGER_ROOT
    if root.is_symlink() or any(p.is_symlink() for p in [root.parent, root.parent.parent]):
        raise ValueError('Ledger symlink refused')
    lock = os.open(root / 'execution.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger = validate_prior(plan)
        secret = key if key is not None else guard._key(ROOT / 'data/private/openai_api_key')
        model = availability if availability is not None else original.provider_check(secret)
        if model.get('available') is not True:
            return {'status': 'provider_unavailable', 'new_inference_requests': 0,
                    'http_status': model.get('http_status')}
        recovery = root / 'recovery-v1'
        recovery.mkdir(mode=0o700)  # Existing or interrupted recovery must never replay.
        snapshot = recovery / 'prior-ledger.json'
        with snapshot.open('xb') as handle:
            os.chmod(snapshot, 0o600)
            handle.write((root / 'ledger.json').read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        ledger['recovery_v1'] = {'plan_sha256': guard._sha(PLAN), 'status': 'running',
                                 'prior_ledger_sha256': EXPECTED_LEDGER}
        guard._write(root / 'ledger.json', ledger)
        analysis, hypotheses, baseline, audits, diagnostics = None, [], [], [], []
        halted = False
        with guard._environment_key(secret):
            for kind in ('analysis', 'hypothesis'):
                if kind == 'hypothesis':
                    baseline = original.recommend([{'id': original.SID, 'title': original.SID,
                        'duration': freeze['measured']['duration'], 'synthetic': False,
                        'analysis': analysis}], [])
                if ledger['reserved_cents'] + 10 > 30 or len(ledger['attempts']) >= 3:
                    raise ValueError('Recovery reservation ceiling reached')
                attempt = {'operation_id': 'recovery-v1-' + kind, 'status': 'pending',
                           'reservation_cents': 10, 'started_at_unix': time.time()}
                ledger['attempts'].append(attempt)
                ledger['reserved_cents'] += 10
                guard._write(root / 'ledger.json', ledger)
                transport = transport_factory(secret)
                captured = {}
                started = time.monotonic()
                def send(payload):
                    guard._request_cap(payload)
                    captured['request'] = payload
                    result = transport(payload)
                    captured['response'] = result
                    return result
                try:
                    if kind == 'analysis':
                        result, audit = original.provider.analyze(original.PACKET / 'source.mp4',
                            freeze['measured'], frames, authorized=True, transport=send, transcribe=False)
                        analysis = result
                    else:
                        result, audit = original.provider.propose(baseline, authorized=True, transport=send)
                        hypotheses = result
                    captured.update(result=result, audit=audit,
                                    baseline=baseline if kind == 'hypothesis' else None)
                    audits.append(audit)
                    attempt['status'] = 'succeeded'
                    if not original.usage_ok(audit):
                        halted = True
                except Exception as exc:
                    # Preserve precise, redacted diagnostics even without a parsed response.
                    telemetry = getattr(transport, 'telemetry', {})
                    attempt['status'] = 'failed' if captured.get('response') is not None or telemetry.get('http_status') else 'unknown'
                    captured.update(error_type=type(exc).__name__, error=safe_text(exc, secret))
                    halted = True
                captured['transport'] = getattr(transport, 'telemetry', {})
                diagnostics.append({'operation': kind, **captured['transport'],
                                    'error': captured.get('error')})
                attempt['duration_ms'] = round((time.monotonic() - started) * 1000)
                artifact = recovery / f'attempt-{kind}.json'
                guard._write(artifact, captured, secret)
                attempt.update(artifact=str(artifact.relative_to(root)), artifact_sha256=guard._sha(artifact))
                ledger['recovery_v1']['status'] = 'halted' if halted else 'running'
                guard._write(root / 'ledger.json', ledger)
                if halted:
                    break
        ledger['recovery_v1']['status'] = 'halted' if halted else 'completed'
        guard._write(root / 'ledger.json', ledger)
        known = len(audits) == len(ledger['attempts']) - 1 and all(original.usage_ok(a) for a in audits)
        report = {'protocol': 'open-media-recovery-v1', 'status': ledger['recovery_v1']['status'],
                  'source': freeze['source'], 'source_count': 1, 'frames': len(frames),
                  'model': original.provider.MODEL, 'prior_unknown_attempts': 1,
                  'new_attempts': len(ledger['attempts']) - 1,
                  'new_schema_accepted': sum(a['status'] == 'succeeded' for a in ledger['attempts'][1:]),
                  'total_reserved_usd': ledger['reserved_cents'] / 100,
                  'new_usage_cost_estimate_usd': round(sum(a['cost_usd'] for a in audits), 8) if known else None,
                  'total_usage_cost_usd': None, 'billing_reconciliation': 'original attempt charge unknown',
                  'diagnostics': diagnostics, 'evaluation': original.evaluate(analysis, hypotheses, baseline, freeze),
                  'plan_sha256': guard._sha(PLAN), 'prior_ledger_sha256': EXPECTED_LEDGER,
                  'runtime_sha256': plan['runtime'], 'limitations': original.LIMITATIONS}
        guard._write(recovery / 'summary.json', report, secret)
        output = ROOT / 'artifacts/verification/open_media_recovery.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        guard._write(output, report, secret)
        return report
    finally:
        os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--prepare', action='store_true')
    actions.add_argument('--execute', action='store_true')
    actions.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.prepare:
            result = prepare()
        elif args.execute:
            result = execute()
        else:
            plan, _, _ = check_plan()
            validate_prior(plan)
            result = {'status': 'ready', 'new_inference_requests': 0}
        print(json.dumps(result, indent=2))
        return 0 if result['status'] in ('ready', 'prepared', 'completed') else 2
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc) if isinstance(exc, ValueError)
                          else 'File or lock operation failed; no automatic replay.'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
