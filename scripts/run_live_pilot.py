#!/usr/bin/env python3
"""Execute the frozen Creative Experiments pilot after human/source gates.

No automatic retries. One canonical project ledger covers every packet and run.
"""
from __future__ import annotations
import argparse
import base64
import contextlib
import csv
import fcntl
import hashlib
import io
import json
import math
import os
import stat
import sys
import time
import uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from app import provider
from app.media import probe
from app.research import recommend
LEDGER_ROOT = ROOT / 'data/private/ce-live-pilot-ledger'
FROZEN_CODE = ['app/media.py', 'app/provider.py', 'scripts/prepare_live_pilot.py', 'configs/live_pilot_v1.json', 'docs/live_pilot.md']
REVIEW_COLUMNS = ['source_id', 'frame_index', 'timestamp_seconds', 'hook_category', 'observation_kind', 'visible_text', 'supported_description', 'reviewer', 'notes']


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path, limit: int=12 * 1024 * 1024):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError(f'Invalid or oversized packet/ledger file: {path.name}')

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON number')))


def _local(root: Path, relative: str) -> Path:
    root = root.resolve(strict=True)
    if not isinstance(relative, str):
        raise ValueError('Invalid relative packet path')
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or '\\' in relative:
        raise ValueError('Packet path traversal refused')
    current = root
    for component in path.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError('Packet symlinks are refused')
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError('Packet path escapes its root')
    return resolved


def _request_cap(request: dict) -> None:
    if request.get('model') != provider.MODEL or request.get('max_output_tokens') != 1200 or request.get('store') is not False:
        raise ValueError('Request model, output cap or storage policy differs from approved pilot')
    text_bytes = 0
    image_count = 0
    for item in request.get('input', []):
        content = item.get('content', [])
        if isinstance(content, str):
            text_bytes += len(content.encode('utf8'))
            continue
        for part in content:
            if part.get('type') == 'input_text':
                text_bytes += len(part.get('text', '').encode('utf8'))
            elif part.get('type') == 'input_image':
                image_count += 1
                url = part.get('image_url', '')
                if part.get('detail') != 'low' or not url.startswith('data:image/jpeg;base64,'):
                    raise ValueError('Only prepared low-detail inline JPEGs are allowed')
                image_bytes = base64.b64decode(url.split(',', 1)[1], validate=True)
                if len(image_bytes) > 512 * 1024:
                    raise ValueError('Image exceeds prepared input cap')
                with Image.open(io.BytesIO(image_bytes)) as image:
                    if max(image.size) > 512:
                        raise ValueError('Image side exceeds 512 pixels')
            else:
                raise ValueError('Unexpected request content type')
    # Bound text bytes plus eight low-detail image inputs under the 20k plan.
    # The provider schema is fixed and checked through frozen source hashes.
    if text_bytes > 12000 or image_count > 8:
        raise ValueError('Prepared request exceeds reviewed input allowance')


def check_packet(directory: Path) -> dict:
    """Read-only offline preflight: no key, network or ledger access."""
    directory = Path(directory).resolve(strict=True)
    freeze = _json(directory / 'freeze.json')
    config = _json(ROOT / 'configs/live_pilot_v1.json')
    if freeze.get('config') != config or freeze.get('protocol_id') != config['protocol_id']:
        raise ValueError('Frozen configuration differs from the approved pilot')
    if config['model'] != provider.MODEL or config['prompt_version'] != provider.PROMPT_VERSION:
        raise ValueError('Pinned model/prompt changed; no silent migration allowed')
    if config['maximum_total_attempts'] != 50 or config['reservation_usd_per_attempt'] != 0.1 or config['creative_experiments_reserved_limit_usd'] != 5 or (config['automatic_retries'] != 0):
        raise ValueError('Budget differs from the reviewed 50 attempts / $5 ceiling')
    hashes = freeze.get('code_sha256', {})
    if set(hashes) != set(FROZEN_CODE):
        raise ValueError('Incomplete frozen source-code inventory')
    for name, digest in hashes.items():
        if _sha(ROOT / name) != digest:
            raise ValueError(f'Frozen source changed: {name}')
    if _sha(_local(directory, 'sources_manifest.csv')) != freeze.get('manifest_sha256'):
        raise ValueError('Source manifest hash changed')
    sources = freeze.get('sources')
    if not isinstance(sources, list) or not 1 <= len(sources) <= 20:
        raise ValueError('Require 1–20 prepared sources')
    identifiers = set()
    content_hashes = set()
    expected_rows = {}
    operations = []
    for source in sources:
        sid = source['source_id']
        if sid in identifiers:
            raise ValueError('Repeated source ID')
        identifiers.add(sid)
        media = _local(directory, source['media_path'])
        digest = _sha(media)
        if digest != source['source_sha256'] or digest in content_hashes:
            raise ValueError('Changed or duplicated source media')
        content_hashes.add(digest)
        metadata = probe(media)
        if metadata != source['measured']:
            raise ValueError('Frozen measured video properties changed')
        records = source['frames']
        frames = []
        if len(records) != 8 or len({f['index'] for f in records}) != 8:
            raise ValueError('Require exactly eight unique prepared frames')
        for record in records:
            path = _local(directory, record['path'])
            if _sha(path) != record['sha256']:
                raise ValueError('Prepared evidence frame changed')
            frames.append({'path': path, 'time': record['time'], 'index': record['index']})
            expected_rows[sid, str(record['index'])] = float(record['time'])
        request_path = _local(directory, source['request_path'])
        if _sha(request_path) != source['request_sha256']:
            raise ValueError('Prepared model request changed')
        expected_request, audit = provider.prepare_request(metadata, frames)
        request = _json(request_path)
        if request != expected_request or audit != source['request_audit']:
            raise ValueError('Request no longer matches prepared evidence')
        _request_cap(request)
        for repetition in (1, 2):
            operations.append({'operation_id': f'{sid}-analysis-{repetition}', 'source_id': sid, 'repetition': repetition, 'kind': 'visual_analysis', 'request_path': source['request_path'], 'request_sha256': source['request_sha256'], 'status': 'prepared_not_executed', 'reservation_usd': 0.1})
    if freeze.get('analysis_operations') != operations:
        raise ValueError('Frozen analysis operation plan changed')
    expected_hypotheses = [{'operation_id': f'hypothesis-group-{i + 1}-repeat-{repetition}', 'source_ids': group, 'repetition': repetition, 'kind': 'exploratory_hypothesis', 'status': 'inputs_pending_real_analysis', 'reservation_usd': 0.1} for i, group in enumerate([sorted(identifiers)[j::3] for j in range(3)]) if group for repetition in (1, 2)]
    if freeze.get('hypothesis_operations') != expected_hypotheses:
        raise ValueError('Frozen hypothesis plan changed')
    confirmation = _json(directory / 'source_confirmation.json', 128 * 1024)
    if not isinstance(confirmation.get('reviewer'), str) or not confirmation['reviewer'].strip():
        raise ValueError('Human source provenance reviewer is missing')
    confirmations = confirmation.get('sources', [])
    if len(confirmations) != len(identifiers) or {item.get('source_id') for item in confirmations} != identifiers:
        raise ValueError('Source confirmations are incomplete or duplicated')
    independent = True
    for item in confirmations:
        if item.get('lawful_api_analysis_confirmed') is not True or item.get('rights_reference_reviewed') is not True:
            raise ValueError('Human confirmation of source rights and lawful API analysis is required')
        value = item.get('independent_original_recording_confirmed')
        if value is not True:
            if value is not False and value is not None:
                raise ValueError('Independence must be true, false or unknown')
            if not isinstance(item.get('notes'), str) or not item['notes'].strip():
                raise ValueError('Explain unconfirmed/related recording independence in notes; never force a false confirmation')
            independent = False
    labels_path = _local(directory, 'human_review.csv')
    if labels_path.stat().st_size > 1024 * 1024:
        raise ValueError('Human label file exceeds limit')
    with labels_path.open(newline='') as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames != REVIEW_COLUMNS:
            raise ValueError('Human review columns changed')
        labels = list(reader)
    if len(labels) != len(expected_rows):
        raise ValueError('Complete human review for every prepared frame first')
    reviewed = set()
    for label in labels:
        if None in label or any((v is None for v in label.values())):
            raise ValueError('Malformed human-review row')
        key = (label['source_id'], label['frame_index'])
        if key not in expected_rows or key in reviewed:
            raise ValueError('Human review references an unknown/repeated frame')
        reviewed.add(key)
        try:
            timestamp = float(label['timestamp_seconds'])
        except ValueError:
            raise ValueError('Invalid human-review timestamp') from None
        if not math.isfinite(timestamp) or abs(timestamp - expected_rows[key]) > 1e-05:
            raise ValueError('Human-review timestamp differs from frozen evidence')
        if label['hook_category'] not in {'', 'preparation', 'packaging', 'other', 'unknown'} or not label['reviewer'].strip():
            raise ValueError('Complete human review and reviewer names before inference')
        if not label['hook_category'] and (not label['notes'].strip()):
            raise ValueError('Explain an uncertain blank hook label in notes')
        if label['observation_kind'] not in {'', 'hook', 'scene', 'product', 'text', 'cta'}:
            raise ValueError('Unknown human observation kind')
        if not label['supported_description'].strip() and (not label['notes'].strip()):
            raise ValueError('Record a supported description or explain uncertainty in notes')
        if any((len(value) > 4000 for value in label.values())):
            raise ValueError('Human review cell exceeds length limit')
    binding = {'packet': str(directory), 'freeze_sha256': _sha(directory / 'freeze.json'), 'human_review_sha256': _sha(labels_path), 'source_confirmation_sha256': _sha(directory / 'source_confirmation.json'), 'runner_sha256': _sha(Path(__file__)), 'baseline_sha256': _sha(ROOT / 'app/research.py')}
    return {'status': 'ready_for_authorized_execution', 'sources': len(sources), 'human_review_rows': len(labels), 'blank_hook_rows_excluded': sum((not row['hook_category'] for row in labels)), 'analysis_attempts': len(operations), 'hypothesis_attempts': len(expected_hypotheses), 'independence': 'reviewer_confirmed' if independent else 'not_established_integration_only', 'binding': binding, 'external_api_calls': 0}


def _write(path: Path, value: dict, secret: str='') -> None:
    if path.is_symlink():
        raise ValueError('Ledger/output symlinks are refused')
    serialized = json.dumps(value, indent=2, allow_nan=False)
    if secret:
        serialized = serialized.replace(secret, '[redacted]')
    temporary = path.parent / ('.' + path.name + '-' + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 384)
    try:
        with os.fdopen(descriptor, 'w') as handle:
            handle.write(serialized + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _key(key_file: Path | None) -> str:
    if key_file is None:
        value = os.environ.get('OPENAI_API_KEY', '')
    else:
        path = Path(key_file)
        if path.is_symlink():
            raise ValueError('Key file symlink refused')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 384 or (info.st_size > 4096):
                raise ValueError('Key file must be an owned regular file with mode 0600')
            value = os.read(descriptor, 4096).decode('ascii').strip()
        finally:
            os.close(descriptor)
    if not value.startswith('sk-') or len(value) < 20 or len(value) > 512 or any((ch.isspace() for ch in value)):
        raise ValueError('Configure a valid-form OpenAI API key outside chat')
    return value


@contextlib.contextmanager

def _environment_key(secret: str):
    previous = os.environ.get('OPENAI_API_KEY')
    os.environ['OPENAI_API_KEY'] = secret
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('OPENAI_API_KEY', None)
        else:
            os.environ['OPENAI_API_KEY'] = previous


def _ledger_check(ledger: dict, binding: dict):
    if ledger.get('binding') != binding:
        raise ValueError('Packet, labels, confirmations or runner changed after execution started; budget cannot be reset')
    attempts = ledger.get('attempts')
    if not isinstance(attempts, list) or len(attempts) > 50 or ledger.get('reserved_cents') != len(attempts) * 10 or (ledger.get('limit_cents') != 500):
        raise ValueError('Invalid spending ledger')
    if any(item.get('status') not in {'pending', 'unknown', 'failed', 'succeeded'}
           or item.get('reservation_cents') != 10 for item in attempts):
        raise ValueError('Invalid attempt status or reservation in spending ledger')
    if len({item.get('operation_id') for item in attempts}) != len(attempts):
        raise ValueError('Repeated operation in ledger')
    if any((item.get('status') in {'pending', 'unknown'} for item in attempts)):
        raise ValueError('A previous request has an unknown outcome; automatic resume is blocked for billing review')
    if ledger.get('halted'):
        raise ValueError('Ledger halted for usage/budget review; no further requests allowed')


def evaluate_saved(directory: Path, freeze: dict, outcomes: dict) -> dict:
    """Mechanical checks against supplied human labels, never a model grader."""
    with (directory / 'human_review.csv').open(newline='') as handle:
        labels = {(row['source_id'], int(row['frame_index'])): row for row in csv.DictReader(handle)}
    sources = {source['source_id']: source for source in freeze['sources']}
    rows = []
    references_valid = references_total = hypothesis_valid = hypothesis_total = 0
    matched = comparisons = baseline_matched = 0
    excluded_sources = []
    repeated_sources = repeated_agreements = 0
    for sid, source in sources.items():
        first = min(source['frames'], key=lambda frame: frame['time'])
        human = labels[sid, first['index']]['hook_category']
        scored = human in {'preparation', 'packaging', 'other'}
        if not scored:
            excluded_sources.append(sid)
        predictions = []
        frame_times = {frame['index']: frame['time'] for frame in source['frames']}
        for repetition in (1, 2):
            result = outcomes.get(f'{sid}-analysis-{repetition}')
            if result is None:
                continue
            predicted = result['hook_category']
            predictions.append(predicted)
            if scored:
                comparisons += 1
                matched += predicted == human
                baseline_matched += human == 'other'
            for segment in result['segments']:
                references_total += 1
                index = segment.get('frame_index')
                references_valid += index in frame_times and abs(segment['start'] - frame_times[index]) < 1e-05
        if len(predictions) == 2:
            repeated_sources += 1
            repeated_agreements += predictions[0] == predictions[1]
        rows.append({'source_id': sid, 'first_frame_index': first['index'], 'human_hook': human or None, 'scored': scored, 'predictions': predictions})
    for operation in freeze['hypothesis_operations']:
        for recommendation in outcomes.get(operation['operation_id'], []):
            for reference in recommendation.get('sources', []):
                hypothesis_total += 1
                source = sources.get(reference.get('video_id'))
                hypothesis_valid += bool(source and reference['video_id'] in operation['source_ids'] and (0 <= reference.get('start', -1) < reference.get('end', -1) <= source['measured']['duration']))
    return {'human_hook_comparison': {'rows': rows, 'matched': matched, 'comparisons': comparisons, 'accuracy': matched / comparisons if comparisons else None, 'excluded_unknown_or_blank_sources': excluded_sources, 'baseline': {'rule': 'Always other', 'matched': baseline_matched, 'comparisons': comparisons, 'accuracy': baseline_matched / comparisons if comparisons else None}, 'denominator_note': 'Repeated calls share one source; comparisons are not independent samples.'}, 'analysis_references': {'valid': references_valid, 'total': references_total}, 'hypothesis_references': {'valid': hypothesis_valid, 'total': hypothesis_total}, 'repeat_consistency': {'agreeing_sources': repeated_agreements, 'sources_with_two_results': repeated_sources}, 'qualitative_review_status': 'pending_human_review', 'limitations': ['A valid source/time reference does not establish that its description is true.', 'Unsupported descriptions, useful hypotheses and edit specificity require human review.', 'Blank and unknown human hook labels are excluded from hook accuracy.', 'No engagement data, causal effect or statistical significance is estimated.']}


def run(directory: Path, *, key_file=None, transport=None) -> dict:
    """Run a gated packet. Test transport receives exact requests; no automatic retry."""
    preflight = check_packet(directory)
    directory = Path(directory).resolve(strict=True)
    ledger_root = Path(LEDGER_ROOT)
    if ledger_root.is_symlink() or any((parent.is_symlink() for parent in [ledger_root.parent, ledger_root.parent.parent])):
        raise ValueError('Ledger directory symlinks are refused')
    ledger_root.mkdir(parents=True, exist_ok=True, mode=448)
    os.chmod(ledger_root, 448)
    lock = os.open(ledger_root / 'execution.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 384)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another pilot execution holds the exclusive process lock') from None
        ledger_path = ledger_root / 'ledger.json'
        origin = ledger_root / 'origin.json'
        if ledger_path.exists() != origin.exists():
            raise ValueError('Incomplete/deleted ledger state; do not reset a spent budget')
        if ledger_path.exists():
            ledger = _json(ledger_path)
            if _json(origin).get('binding') != preflight['binding']:
                raise ValueError('This budget is already bound to another immutable packet')
            _ledger_check(ledger, preflight['binding'])
        else:
            if any(ledger_root.glob('attempt-*.json')):
                raise ValueError('Prior attempt artifacts exist without ledger; refusing budget reset')
            ledger = {'binding': preflight['binding'], 'limit_cents': 500, 'reserved_cents': 0, 'attempts': [], 'halted': False}
            _write(origin, {'binding': preflight['binding']})
            _write(ledger_path, ledger)
        secret = _key(Path(key_file) if key_file is not None else None)
        freeze = _json(directory / 'freeze.json')
        sources = {s['source_id']: s for s in freeze['sources']}
        operations = freeze['analysis_operations'] + freeze['hypothesis_operations']
        outcomes = {}
        for attempt in ledger['attempts']:
            evidence = _json(_local(ledger_root, attempt['artifact']))
            if _sha(_local(ledger_root, attempt['artifact'])) != attempt['artifact_sha256']:
                raise ValueError('Saved attempt evidence changed')
            if attempt['status'] == 'succeeded':
                outcomes[attempt['operation_id']] = evidence['result']
        already = {item['operation_id'] for item in ledger['attempts']}
        with _environment_key(secret):
            for operation in operations:
                oid = operation['operation_id']
                if oid in already:
                    continue
                if len(ledger['attempts']) >= 50 or ledger['reserved_cents'] + 10 > 500:
                    raise ValueError('Creative Experiments attempt/spend ceiling reached')
                source = sources.get(operation.get('source_id'))
                candidates = None
                if source:
                    metadata = source['measured']
                    frames = [{'path': _local(directory, r['path']), 'index': r['index'], 'time': r['time']} for r in source['frames']]
                    request, _ = provider.prepare_request(metadata, frames)
                    _request_cap(request)
                    if request != _json(_local(directory, source['request_path'])):
                        raise ValueError('Prepared request changed before sending')
                else:
                    videos = []
                    for sid in operation['source_ids']:
                        analysis = outcomes.get(f"{sid}-analysis-{operation['repetition']}")
                        if analysis is None:
                            continue
                        videos.append({'id': sid, 'title': sid, 'duration': sources[sid]['measured']['duration'], 'synthetic': False, 'analysis': analysis})
                    if not videos:
                        continue
                    candidates = recommend(videos, [])
                attempt = {'operation_id': oid, 'kind': operation['kind'], 'status': 'pending', 'reservation_cents': 10, 'started_at_unix': time.time()}
                ledger['attempts'].append(attempt)
                ledger['reserved_cents'] += 10
                _write(ledger_path, ledger)
                started = time.monotonic()
                response_holder = {}
                sent = {}

                def send(payload):
                    _request_cap(payload)
                    sent['request'] = payload
                    response = transport(payload) if transport is not None else provider._post_json(payload, secret)
                    response_holder['response'] = response
                    return response
                try:
                    if source:
                        result, audit = provider.analyze(_local(directory, source['media_path']), metadata, frames, authorized=True, transport=send, transcribe=False)
                    else:
                        result, audit = provider.propose(candidates, authorized=True, transport=send)
                    cost = audit.get('cost_usd')
                    attempt['status'] = 'succeeded'
                    outcomes[oid] = result
                    if cost is None or not math.isfinite(cost) or cost > 0.1 or (audit.get('input_tokens') is None) or (audit['input_tokens'] > 20000) or (audit.get('output_tokens') is None) or (audit['output_tokens'] > 1200):
                        ledger['halted'] = True
                    evidence = {'operation': operation, 'result': result, 'audit': audit, 'request': sent.get('request'), 'response': response_holder.get('response'), 'duration_ms': round((time.monotonic() - started) * 1000), 'independence': preflight['independence']}
                except Exception as exc:
                    attempt['status'] = 'failed' if response_holder else 'unknown'
                    ledger['halted'] = True
                    evidence = {'operation': operation, 'result': None, 'error_type': type(exc).__name__, 'error': 'Provider operation failed validation or transmission; inspect private evidence and billing before any recovery.', 'request': sent.get('request'), 'response': response_holder.get('response'), 'duration_ms': round((time.monotonic() - started) * 1000)}
                attempt['artifact'] = f"attempt-{len(ledger['attempts']):03d}.json"
                artifact = ledger_root / attempt['artifact']
                _write(artifact, evidence, secret)
                attempt['artifact_sha256'] = _sha(artifact)
                _write(ledger_path, ledger)
                if ledger['halted']:
                    raise ValueError('Pilot halted after an uncertain, invalid or over-reservation outcome; no automatic recovery request sent')
        summary = {'status': 'completed', 'packet': str(directory), 'ledger': str(ledger_root), 'attempts': len(ledger['attempts']), 'reserved_usd': ledger['reserved_cents'] / 100, 'usage_cost_usd': sum(((_json(_local(ledger_root, item['artifact'])).get('audit') or {}).get('cost_usd', 0) or 0 for item in ledger['attempts'])), 'sources': len(sources), 'independence': preflight['independence'], 'limitations': ['Exploratory integration pilot, not engagement or causal effectiveness evidence.', 'Related or unconfirmed recordings must not be counted as independent evidence.', 'No publication metrics were invented; hypothesis requests remain exploratory.']}
        summary['evaluation'] = evaluate_saved(directory, freeze, outcomes)
        _write(ledger_root / 'summary.json', summary, secret)
        return summary
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--key-file', type=Path, default=None, help='Explicit owned mode-0600 key file; otherwise use OPENAI_API_KEY')
    args = parser.parse_args()
    try:
        result = check_packet(args.directory) if args.check_only else run(args.directory, key_file=args.key_file)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc), 'external_api_calls': 0 if args.check_only else None}))
        raise SystemExit(2) from None
    print(json.dumps(result, indent=2))
if __name__ == '__main__':
    main()
