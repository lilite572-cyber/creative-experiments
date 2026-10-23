#!/usr/bin/env python3
"""One-shot, prospectively frozen integration check; no human-quality claims."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from app import media, provider
from app.research import recommend
import run_live_pilot as guard
from run_authorized_pilots import provider_check

PACKET = ROOT / 'data/private/open-media-integration-v1'
SOURCE_URL = 'https://upload.wikimedia.org/wikipedia/commons/3/34/Coffee_Bean_%26_Tea_Leaf_Process.webm'
SOURCE_PAGE = 'https://commons.wikimedia.org/wiki/File:Coffee_Bean_%26_Tea_Leaf_Process.webm'
SOURCE_SHA1 = '0a3ca2cf4b1aba86546834edb86db225e44558f6'
SID = 'commons-kelliks-coffee-2013'
CODE = ['scripts/run_open_media_check.py', 'scripts/run_live_pilot.py',
        'scripts/run_authorized_pilots.py', 'app/provider.py', 'app/media.py',
        'app/research.py', 'docs/open_media_integration_v1.md']
LIMITATIONS = [
    'One convenience source; no human reference labels for this check.',
    'Reference validity is not factual accuracy or human agreement.',
    'No publication metrics, engagement effect or successful creative pattern established.',
    'One analysis and one wording operation do not measure repeatability.',
    'Source converted to silent 24 fps MP4; model received eight downscaled stills only.',
]


def prepare():
    if PACKET.exists() or PACKET.is_symlink():
        raise ValueError('Packet already exists; never overwrite frozen inputs')
    PACKET.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=PACKET.parent, prefix='.open-media-') as temp:
        directory = Path(temp) / 'packet'
        directory.mkdir(mode=0o700)
        original = directory / 'original.webm'
        request = urllib.request.Request(SOURCE_URL, headers={'User-Agent': 'CreativeExperiments/1.0'})
        with urllib.request.urlopen(request, timeout=30) as response, original.open('wb') as output:
            total = 0
            while chunk := response.read(65536):
                total += len(chunk)
                if total > 8 * 1024 * 1024:
                    raise ValueError('Source download exceeds its bound')
                output.write(chunk)
        if total != 7032288 or hashlib.sha1(original.read_bytes()).hexdigest() != SOURCE_SHA1:
            raise ValueError('Source differs from the prospectively selected Commons original')
        path = directory / 'source.mp4'
        media._run(['-protocol_whitelist', 'file,pipe', '-f', 'matroska', '-i', str(original),
                    '-map', '0:v:0', '-an', '-vf', 'fps=24', '-c:v', 'libx264',
                    '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart', '-n', str(path)])
        metadata = media.probe(path)
        frames = media.extract_frames(path, directory / 'frames')
        request, audit = provider.prepare_request(metadata, frames)
        guard._request_cap(request)
        guard._write(directory / 'request.json', request)
        credit = {'title': 'Coffee Bean & Tea Leaf Process', 'author': 'Kelliks',
                  'source_url': SOURCE_PAGE, 'license': 'CC BY-SA 3.0',
                  'license_url': 'https://creativecommons.org/licenses/by-sa/3.0/',
                  'assessment': 'Assistant reviewed source and license; not a human attestation',
                  'modifications': 'Silent 24 fps H.264 conversion; eight JPEG frame extracts',
                  'source_id': SID}
        guard._write(directory / 'attribution.json', credit)
        freeze = {'protocol': 'open-media-integration-v1', 'prepared_at_unix': time.time(),
                  'source': credit, 'measured': metadata, 'request_audit': audit,
                  'frames': [{'path': str(f['path'].relative_to(directory)), 'index': f['index'],
                              'time': f['time']} for f in frames],
                  'files': {str(p.relative_to(directory)): guard._sha(p)
                            for p in directory.rglob('*') if p.is_file()},
                  'code': {name: guard._sha(ROOT / name) for name in CODE},
                  'operations': ['analysis', 'hypothesis'], 'max_reserved_usd': 0.2,
                  'human_labels': None, 'limitations': LIMITATIONS}
        guard._write(directory / 'freeze.json', freeze)
        directory.rename(PACKET)
    return {'status': 'prepared', 'source_count': 1, 'frames': 8, 'inference_requests': 0}


def check_packet():
    freeze = guard._json(PACKET / 'freeze.json')
    if (freeze.get('protocol') != 'open-media-integration-v1'
            or freeze.get('operations') != ['analysis', 'hypothesis']
            or freeze.get('max_reserved_usd') != 0.2
            or freeze.get('human_labels') is not None):
        raise ValueError('Unexpected protocol, operations or budget')
    if set(freeze['code']) != set(CODE):
        raise ValueError('Incomplete runtime inventory')
    required_files = {'original.webm', 'source.mp4', 'request.json', 'attribution.json'} | {
        f['path'] for f in freeze['frames']}
    if set(freeze['files']) != required_files or len(required_files) != 12:
        raise ValueError('Incomplete source/frame inventory')
    for name, digest in freeze['code'].items():
        if guard._sha(ROOT / name) != digest:
            raise ValueError('Runtime/protocol changed after preparation')
    for name, digest in freeze['files'].items():
        if guard._sha(guard._local(PACKET, name)) != digest:
            raise ValueError('Prepared evidence changed')
    if hashlib.sha1((PACKET / 'original.webm').read_bytes()).hexdigest() != SOURCE_SHA1:
        raise ValueError('Unexpected original source')
    if media.probe(PACKET / 'source.mp4') != freeze['measured']:
        raise ValueError('Measured metadata changed')
    frames = [{**f, 'path': guard._local(PACKET, f['path'])} for f in freeze['frames']]
    if len(frames) != 8:
        raise ValueError('Require eight sampled frames')
    request, audit = provider.prepare_request(freeze['measured'], frames)
    guard._request_cap(request)
    if request != guard._json(PACKET / 'request.json') or audit != freeze['request_audit']:
        raise ValueError('Request no longer matches evidence')
    return freeze, frames


def usage_ok(audit):
    counts = (audit.get('input_tokens'), audit.get('output_tokens'))
    cost = audit.get('cost_usd')
    return (all(type(n) is int and n >= 0 for n in counts)
            and counts[0] <= 20000 and counts[1] <= 1200
            and type(cost) in (float, int) and math.isfinite(cost) and 0 <= cost <= 0.1)


def evaluate(analysis, hypotheses, baseline, freeze):
    times = {f['index']: f['time'] for f in freeze['frames']}
    segments = analysis.get('segments', []) if analysis else []
    references = [r for h in hypotheses for r in h.get('sources', [])]
    by_id = {b['id']: b for b in baseline}
    return {
        'analysis_references': {'total': len(segments), 'valid': sum(
            s['frame_index'] in times and abs(s['start'] - times[s['frame_index']]) < 1e-5
            for s in segments)},
        'hypothesis_references': {'total': len(references), 'valid': sum(
            r.get('video_id') == SID and 0 <= r.get('start', -1) < r.get('end', -1)
            <= freeze['measured']['duration'] for r in references)},
        'baseline_candidates': len(baseline), 'model_hypotheses': len(hypotheses),
        'programmatic_fields_preserved': all(h['id'] in by_id and all(
            h.get(k) == v for k, v in by_id[h['id']].items()
            if k not in {'hypothesis', 'change', 'preserve'}) for h in hypotheses)
            if hypotheses else None,
        'human_quality_assessment': 'not_performed', 'publication_metrics': None,
    }


def execute(*, transport=None, key=None, availability=None):
    freeze, frames = check_packet()
    ledger_root = guard.LEDGER_ROOT
    if ledger_root.is_symlink() or any(p.is_symlink() for p in [ledger_root.parent, ledger_root.parent.parent]):
        raise ValueError('Ledger symlink refused')
    ledger_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = os.open(ledger_root / 'execution.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if any(p.name != 'execution.lock' for p in ledger_root.iterdir()):
            raise ValueError('CE ledger already contains a run; do not reset or automatically replay it')
        secret = key if key is not None else guard._key(ROOT / 'data/private/openai_api_key')
        available = availability if availability is not None else provider_check(secret)
        if available.get('available') is not True:
            return {'status': 'provider_unavailable', 'inference_requests': 0,
                    'detail': 'Metadata check failed; this does not establish an invalid key.'}
        binding = {'protocol': freeze['protocol'], 'freeze_sha256': guard._sha(PACKET / 'freeze.json'),
                   'runner_sha256': guard._sha(Path(__file__))}
        ledger = {'binding': binding, 'limit_cents': 500, 'reserved_cents': 0,
                  'attempts': [], 'halted': False, 'run_max_attempts': 2}
        guard._write(ledger_root / 'origin.json', {'binding': binding})
        guard._write(ledger_root / 'ledger.json', ledger)
        analysis, hypotheses, baseline, audits = None, [], [], []
        with guard._environment_key(secret):
            for kind in ['analysis', 'hypothesis']:
                if kind == 'hypothesis':
                    baseline = recommend([{'id': SID, 'title': SID, 'duration': freeze['measured']['duration'],
                                           'synthetic': False, 'analysis': analysis}], [])
                attempt = {'operation_id': kind, 'status': 'pending', 'reservation_cents': 10}
                ledger['attempts'].append(attempt)
                ledger['reserved_cents'] += 10
                guard._write(ledger_root / 'ledger.json', ledger)
                captured = {}
                started = time.monotonic()
                def send(payload):
                    guard._request_cap(payload)
                    captured['request'] = payload
                    response = transport(payload) if transport else provider._post_json(payload, secret)
                    captured['response'] = response
                    return response
                try:
                    if kind == 'analysis':
                        result, audit = provider.analyze(PACKET / 'source.mp4', freeze['measured'], frames,
                                                        authorized=True, transport=send, transcribe=False)
                        analysis = result
                    else:
                        result, audit = provider.propose(baseline, authorized=True, transport=send)
                        hypotheses = result
                    captured.update(result=result, audit=audit, baseline=baseline if kind == 'hypothesis' else None)
                    audits.append(audit)
                    attempt['status'] = 'succeeded'
                    if not usage_ok(audit):
                        ledger['halted'] = True
                except Exception as exc:
                    attempt['status'] = 'failed' if 'response' in captured else 'unknown'
                    ledger['halted'] = True
                    captured.update(error_type=type(exc).__name__, error='Operation failed; no automatic retry. Inspect private evidence and billing.')
                attempt['duration_ms'] = round((time.monotonic() - started) * 1000)
                artifact = ledger_root / f'attempt-{kind}.json'
                guard._write(artifact, captured, secret)
                attempt.update(artifact=artifact.name, artifact_sha256=guard._sha(artifact))
                guard._write(ledger_root / 'ledger.json', ledger)
                if ledger['halted']:
                    break
        known = all(usage_ok(a) for a in audits) and len(audits) == len(ledger['attempts'])
        report = {'protocol': freeze['protocol'], 'status': 'halted' if ledger['halted'] else 'completed',
                  'source': freeze['source'], 'source_count': 1, 'frames': len(frames),
                  'model': provider.MODEL, 'attempted': len(ledger['attempts']),
                  'schema_accepted': sum(a['status'] == 'succeeded' for a in ledger['attempts']),
                  'reserved_usd': ledger['reserved_cents'] / 100,
                  'usage_cost_estimate_usd': round(sum(a['cost_usd'] for a in audits), 8) if known else None,
                  'input_tokens': sum(a['input_tokens'] for a in audits) if known else None,
                  'output_tokens': sum(a['output_tokens'] for a in audits) if known else None,
                  'operations': [{'kind': a['operation_id'], 'status': a['status'], 'duration_ms': a['duration_ms']}
                                 for a in ledger['attempts']],
                  'evaluation': evaluate(analysis, hypotheses, baseline, freeze),
                  'freeze_sha256': binding['freeze_sha256'], 'runtime_sha256': freeze['code'],
                  'media_sha256': freeze['files']['source.mp4'],
                  'cost_basis': 'Returned API tokens at frozen planning rates; not a billing receipt.',
                  'limitations': LIMITATIONS}
        guard._write(ledger_root / 'summary.json', report, secret)
        public = ROOT / 'artifacts/verification/open_media_integration.json'
        public.parent.mkdir(parents=True, exist_ok=True)
        guard._write(public, report, secret)
        return report
    finally:
        os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--execute', action='store_true')
    action.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        result = prepare() if args.prepare else execute() if args.execute else (
            {'status': 'ready', 'source_count': 1, 'frames': len(check_packet()[1]), 'inference_requests': 0})
        print(json.dumps(result, indent=2))
        return 0 if result['status'] in {'ready', 'prepared', 'completed'} else 2
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'blocked', 'error_type': type(exc).__name__,
                          'reason': str(exc) if isinstance(exc, ValueError) else 'File, lock or download operation failed.'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
