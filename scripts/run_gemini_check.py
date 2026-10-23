#!/usr/bin/env python3
"""Separate, one-shot Gemini free-tier integration check; no paid fallback."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import run_open_media_check as original
from app import gemini_provider as gemini

guard = original.guard
PRIVATE = ROOT / 'data/private/gemini-open-media-v1'
KEY = ROOT / 'data/private/gemini_api_key'
PROTOCOL = 'gemini-open-media-v1'
PLAN_NAME = 'plan-key-format-v2.json'
RUNTIME = ['app/gemini_provider.py', 'scripts/run_gemini_check.py', 'docs/gemini_open_media_v1.md',
    'docs/gemini_key_format_v2.md']


def safe_directory(path):
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError('Symlink in private path refused.')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)


def key_digest(key):
    return hashlib.sha256(key.encode()).hexdigest()


def validate_key_input(key):
    # Keys are opaque credentials, not necessarily legacy AIza traffic keys.
    # Accept bounded ASCII token characters, including AQ. auth keys. Only the
    # provider can establish validity. Never echo rejected input.
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{20,4096}', key):
        raise ValueError('Paste the complete API key only, without quotes, spaces or line breaks; nothing saved.')
    return key


def read_key():
    if any(p.is_symlink() for p in [KEY, *KEY.parents]):
        raise ValueError('Key symlink refused.')
    fd = os.open(KEY, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4097):
            raise ValueError('Key must be an owned regular file with mode 0600.')
        key = handle.read().strip()
    return validate_key_input(key)


def configure():
    safe_directory(PRIVATE)
    if KEY.exists() or (PRIVATE / 'authorization.json').exists():
        raise ValueError('Gemini configuration already exists; refusing overwrite.')
    if not sys.stdin.isatty():
        raise ValueError('Use an interactive Terminal to enter the key securely.')
    print('В AI Studio у проекта этого ключа должен быть тариф Free tier, без платного биллинга.')
    print('Будут отправлены 8 кадров открытого ролика CC BY-SA и одна гипотеза; Google может использовать данные для улучшения продуктов.')
    print('Модель: ' + gemini.MODEL + '. Не более двух запросов. Платный тариф и повторы отключены в этом сценарии.')
    answer = input('Подтверждаешь Free tier и этот запуск? Введи FREE: ').strip()
    if answer != 'FREE':
        raise ValueError('Free-tier execution not confirmed; no request sent.')
    key = getpass.getpass('Вставь Gemini API key (ввод скрыт): ').strip()
    validate_key_input(key)
    fd = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(key + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    guard._write(PRIVATE / 'authorization.json', {
        'provider': 'gemini', 'model': gemini.MODEL, 'budget_usd': 0,
        'free_tier_confirmed_by_owner': True, 'public_media_processing_confirmed': True,
        'key_sha256': key_digest(key), 'confirmed_at_unix': time.time()})


def prepare():
    original.check_packet()
    safe_directory(PRIVATE)
    plan_path = PRIVATE / PLAN_NAME
    if (PRIVATE / 'run').exists():
        raise ValueError('An inference run already exists; preparation cannot authorize replay.')
    if plan_path.exists():
        raise ValueError('Plan already exists; do not overwrite frozen protocol.')
    plan = {'protocol': PROTOCOL, 'model': gemini.MODEL, 'budget_usd': 0,
        'setup_revision': 'key-format-v2',
        'previous_plan_sha256': guard._sha(PRIVATE / 'plan.json') if (PRIVATE / 'plan.json').exists() else None,
        'max_attempts': 2, 'automatic_retries': 0,
        'source_freeze_sha256': guard._sha(original.PACKET / 'freeze.json'),
        'prior_openai_ledger_sha256': guard._sha(guard.LEDGER_ROOT / 'ledger.json'),
        'runtime': {p: guard._sha(ROOT / p) for p in RUNTIME},
        'prepared_at_unix': time.time()}
    guard._write(plan_path, plan)
    return {'status': 'prepared', 'model': gemini.MODEL, 'inference_requests': 0}


def check():
    freeze, frames = original.check_packet()
    if any(p.is_symlink() for p in [PRIVATE, *PRIVATE.parents]):
        raise ValueError('Private path symlink refused.')
    plan = guard._json(PRIVATE / PLAN_NAME)
    if (plan.get('protocol') != PROTOCOL or plan.get('model') != gemini.MODEL
            or plan.get('setup_revision') != 'key-format-v2'
            or plan.get('budget_usd') != 0 or plan.get('max_attempts') != 2
            or plan.get('automatic_retries') != 0 or set(plan.get('runtime', {})) != set(RUNTIME)):
        raise ValueError('Unexpected Gemini plan.')
    previous = PRIVATE / 'plan.json'
    if (guard._sha(previous) if previous.exists() else None) != plan.get('previous_plan_sha256'):
        raise ValueError('Previous preparation evidence changed.')
    for path, digest in plan['runtime'].items():
        if guard._sha(ROOT / path) != digest:
            raise ValueError('Gemini runtime or protocol changed after freeze.')
    if (guard._sha(original.PACKET / 'freeze.json') != plan['source_freeze_sha256']
            or guard._sha(guard.LEDGER_ROOT / 'ledger.json') != plan['prior_openai_ledger_sha256']):
        raise ValueError('Prior source or OpenAI evidence changed.')
    if (PRIVATE / 'run').exists():
        raise ValueError('Gemini run already exists; no automatic replay or ledger deletion.')
    return plan, freeze, frames


def execute(transport_factory=gemini.Transport):
    plan, freeze, frames = check()
    key = read_key()
    auth = guard._json(PRIVATE / 'authorization.json')
    if (auth.get('free_tier_confirmed_by_owner') is not True
            or auth.get('public_media_processing_confirmed') is not True
            or auth.get('provider') != 'gemini' or auth.get('model') != gemini.MODEL
            or auth.get('budget_usd') != 0 or auth.get('key_sha256') != key_digest(key)):
        raise ValueError('Matching Free-tier authorization required; no request sent.')
    # Atomic exclusive directory creation blocks concurrent/repeated execution.
    run = PRIVATE / 'run'
    run.mkdir(mode=0o700)
    ledger = {'protocol': PROTOCOL, 'status': 'running', 'attempts': [],
        'plan_sha256': guard._sha(PRIVATE / PLAN_NAME),
        'setup_revision': 'key-format-v2',
        'authorization_sha256': guard._sha(PRIVATE / 'authorization.json'),
        'budget_usd': 0, 'free_tier_basis': 'owner_attestation_not_api_verified'}
    guard._write(run / 'ledger.json', ledger)
    analysis, baseline, hypotheses = None, [], []
    for kind in ('analysis', 'hypothesis'):
        if kind == 'hypothesis':
            baseline = original.recommend([{'id': original.SID, 'title': original.SID,
                'duration': freeze['measured']['duration'], 'synthetic': False, 'analysis': analysis}], [])
        payload = gemini.analysis_request(freeze['measured'], frames) if kind == 'analysis' else gemini.hypothesis_request(baseline)
        capture = {'request': payload, 'baseline': baseline if kind == 'hypothesis' else None}
        attempt = {'operation': kind, 'status': 'pending', 'started_at_unix': time.time()}
        ledger['attempts'].append(attempt)
        guard._write(run / 'ledger.json', ledger)
        transport = transport_factory(key)
        started = time.monotonic()
        try:
            response = transport(payload)
            capture['response'] = response
            parsed, audit = gemini.parse(response)
            result = (gemini.validate_analysis(parsed, freeze['measured'], frames)
                if kind == 'analysis' else gemini.validate_hypotheses(parsed, baseline))
            if kind == 'analysis':
                analysis = result
            else:
                hypotheses = result
            capture.update(result=result, audit=audit)
            attempt.update(status='succeeded', audit=audit)
        except Exception as exc:
            attempt['status'] = 'failed' if 'response' in capture or transport.telemetry.get('http_status') else 'unknown'
            capture['error'] = str(exc).replace(key, '[redacted]')[:800]
            capture['error_type'] = type(exc).__name__
            ledger['status'] = 'halted'
        attempt['duration_ms'] = round((time.monotonic() - started) * 1000)
        capture['transport'] = transport.telemetry
        artifact = run / f'{kind}.json'
        guard._write(artifact, capture, key)
        attempt.update(artifact=artifact.name, artifact_sha256=guard._sha(artifact),
            diagnostics=transport.telemetry, error=capture.get('error'))
        guard._write(run / 'ledger.json', ledger, key)
        if ledger['status'] == 'halted':
            break
    if ledger['status'] != 'halted':
        ledger['status'] = 'completed'
    guard._write(run / 'ledger.json', ledger, key)
    report = {**ledger, 'source': freeze['source'], 'source_count': 1, 'frames': len(frames),
        'model': gemini.MODEL, 'attempted': len(ledger['attempts']),
        'schema_accepted': sum(a['status'] == 'succeeded' for a in ledger['attempts']),
        'expected_free_tier_cost_usd': 0, 'billed_cost_usd': None,
        'billing_note': 'Free tier attested by owner; API does not return a billing receipt.',
        'evaluation': original.evaluate(analysis, hypotheses, baseline, freeze),
        'runtime_sha256': plan['runtime'], 'source_freeze_sha256': plan['source_freeze_sha256'],
        'prior_openai_ledger_sha256': plan['prior_openai_ledger_sha256'],
        'limitations': original.LIMITATIONS + ['Separate Gemini integration check, not an OpenAI comparison or app UI integration.']}
    guard._write(run / 'summary.json', report, key)
    output = ROOT / 'artifacts/verification/gemini_open_media.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    guard._write(output, report, key)
    return json.loads(json.dumps(report).replace(key, '[redacted]'))


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    actions = parser.add_mutually_exclusive_group(required=True)
    for action in ('prepare', 'check-only', 'configure', 'execute', 'start'):
        actions.add_argument('--' + action, action='store_true')
    args = parser.parse_args()
    try:
        if args.prepare:
            result = prepare()
        elif args.check_only:
            check()
            result = {'status': 'ready_for_configuration', 'inference_requests': 0,
                'key_present': KEY.is_file(), 'model': gemini.MODEL}
        elif args.configure:
            check()
            configure()
            result = {'status': 'configured', 'inference_requests': 0}
        else:
            if args.start:
                check()
                if not KEY.exists():
                    configure()
            result = execute()
        print(json.dumps(result, indent=2))
        return 0 if result['status'] in {'prepared', 'configured', 'ready_for_configuration', 'completed'} else 2
    except (ValueError, OSError, EOFError, KeyboardInterrupt) as exc:
        # Never print raw OS errors or credentials.
        reason = str(exc) if isinstance(exc, ValueError) else 'Local setup interrupted or unavailable; no automatic retry.'
        print(json.dumps({'status': 'blocked', 'reason': reason}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
