#!/usr/bin/env python3
"""Attach the verified saved pilot to a separate local workspace; zero API calls."""
import argparse
import copy
import hashlib
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from app import db
import review_gemini_run as review

WORKSPACE = 'verified-open-media-pilot'
VIDEO = 'verified-kelliks-coffee'
OPERATION = 'verified-gemini-analysis-import'


def imported_analysis(original, report):
    analysis = copy.deepcopy(original)
    analysis['mode'] = 'gemini_import'
    analysis['raw_model_hook_category'] = analysis['hook_category']
    analysis['hook_category'] = 'unknown'
    analysis['limitations'] += [
        'Imported saved Gemini response; opening this page sends no new model request.',
        'Not human-validated. The opening category is excluded from pattern calculations pending review.',
        'Review flags: a scene at 19.04 seconds was labeled hook; license credits were labeled CTA.',
        'No publication metrics exist for this source. Any recommendation is exploratory.']
    analysis['review_flags'] = report['semantic_review_flags']
    return analysis


def load(owner_email):
    report = review.review()  # Verifies hashes and replays validation; no network.
    run = review.run
    freeze, _ = run.original.check_packet()
    captured = run.guard._json(run.PRIVATE / 'run/analysis.json')
    analysis = imported_analysis(captured['result'], report)
    db.init()
    source = run.original.PACKET / 'source.mp4'
    source_hash = run.guard._sha(source)
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        owner = connection.execute('SELECT id FROM users WHERE email=?', (owner_email.lower(),)).fetchone()
        if not owner:
            raise ValueError('Owner not found. Run python -m app.demo or register locally first.')
        existing = connection.execute('SELECT owner FROM workspaces WHERE id=?', (WORKSPACE,)).fetchone()
        if existing and existing['owner'] != owner['id']:
            raise ValueError('Pilot workspace belongs to a different owner.')
        video = db.record(connection, WORKSPACE, 'video', VIDEO) if existing else None
        if video:
            if video.get('pilot_source_sha256') != source_hash:
                raise ValueError('Existing pilot source mismatch; refusing overwrite.')
            return {'status': 'already_imported', 'workspace': WORKSPACE, 'video': VIDEO, 'network_requests': 0}
        folder = db.ROOT / WORKSPACE
        run.safe_directory(folder)
        target = folder / 'source.mp4'
        if target.is_symlink():
            raise ValueError('Media symlink refused.')
        if target.exists():
            if run.guard._sha(target) != source_hash:
                raise ValueError('Existing pilot media differs; refusing overwrite.')
        else:
            with source.open('rb') as src, target.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            target.chmod(0o600)
        brand = {'id': WORKSPACE, 'name': 'Open-media pilot', 'synthetic': False,
            'product': 'Licensed coffee footage; saved Gemini interpretation.',
            'audience': 'Technical integration review; no campaign audience data.',
            'goal': 'Inspect source-backed observations and prepare an exploratory edit.'}
        if not existing:
            connection.execute('INSERT INTO workspaces VALUES(?,?,?)', (WORKSPACE, owner['id'], db.pack(brand)))
        value = {'id': VIDEO, 'title': 'Coffee process · recorded Gemini analysis',
            'filename': 'source.mp4', 'path': str(target), 'synthetic': False,
            'analysis': analysis, **freeze['measured'], 'created_at': db.now(),
            'pilot_source_sha256': source_hash, 'provenance': freeze['source'],
            'evidence_summary_sha256': report['original_summary_sha256']}
        db.save(connection, WORKSPACE, 'video', value)
        db.save(connection, WORKSPACE, 'operation', {'id': OPERATION, 'kind': 'saved_analysis_import',
            'status': 'completed', 'input': {'video_id': VIDEO, 'source_sha256': source_hash,
                'summary_sha256': report['original_summary_sha256']},
            'result': {'video_id': VIDEO, 'network_requests': 0}, 'error': None,
            'model': analysis['model'], 'prompt_version': analysis['prompt_version'],
            'duration_ms': 0, 'cost_usd': 0, 'created_at': db.now()})
    return {'status': 'imported', 'workspace': WORKSPACE, 'video': VIDEO, 'network_requests': 0}


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', default='demo@example.test')
    args = parser.parse_args()
    print(json.dumps(load(args.owner), indent=2))
