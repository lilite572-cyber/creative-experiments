#!/usr/bin/env python3
"""Offline, post-hoc review of a completed Gemini run. Never calls an API."""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import run_gemini_check as run


def validate_with_fixed_preservation(result, baseline):
    """Only verbatim, precomputed preservation text may contain digits.

    Apply the frozen validator to all generated prose and references. Preserve
    requirements are immutable here, not a field the model can rewrite.
    """
    by_id = {b['id']: b for b in baseline}
    revised = copy.deepcopy(result)
    if not isinstance(revised, dict) or not isinstance(revised.get('recommendations'), list):
        raise ValueError('Invalid recommendations.')
    for item in revised['recommendations']:
        ident = item.get('candidate_id') if isinstance(item, dict) else None
        if not isinstance(ident, str) or ident not in by_id:
            raise ValueError('Unknown candidate.')
        if item.get('preserve') != by_id[ident]['preserve']:
            raise ValueError('Preservation requirements must match the computed baseline exactly.')
        item['preserve'] = ['Keep the supplied preservation requirements unchanged.']
    accepted = run.gemini.validate_hypotheses(revised, baseline)
    for candidate in accepted:
        candidate['preserve'] = copy.deepcopy(by_id[candidate['id']]['preserve'])
    return accepted


def review():
    directory = run.PRIVATE / 'run'
    summary = run.guard._json(directory / 'summary.json')
    if run.guard._json(ROOT / 'artifacts/verification/gemini_open_media.json') != summary:
        raise ValueError('Public/private original reports disagree.')
    if run.guard._sha(run.PRIVATE / run.PLAN_NAME) != summary['plan_sha256']:
        raise ValueError('Original plan changed.')
    for name, digest in summary['runtime_sha256'].items():
        if run.guard._sha(ROOT / name) != digest:
            raise ValueError('Original runtime changed.')
    if run.guard._sha(run.guard.LEDGER_ROOT / 'ledger.json') != summary['prior_openai_ledger_sha256']:
        raise ValueError('OpenAI evidence changed.')
    if [a['operation'] for a in summary['attempts']] != ['analysis', 'hypothesis']:
        raise ValueError('Expected two preserved attempts.')
    artifacts = {}
    for attempt in summary['attempts']:
        path = run.guard._local(directory, attempt['artifact'])
        if run.guard._sha(path) != attempt['artifact_sha256']:
            raise ValueError('Original response evidence changed.')
        artifacts[attempt['operation']] = run.guard._json(path)
    freeze, frames = run.original.check_packet()
    parsed, analysis_audit = run.gemini.parse(artifacts['analysis']['response'])
    analysis = run.gemini.validate_analysis(parsed, freeze['measured'], frames)
    parsed, hypothesis_audit = run.gemini.parse(artifacts['hypothesis']['response'])
    baseline = artifacts['hypothesis']['baseline']
    try:
        run.gemini.validate_hypotheses(parsed, baseline)
        original_accepted = True
    except ValueError:
        original_accepted = False
    hypotheses = validate_with_fixed_preservation(parsed, baseline)
    usage = [a['usage'] for a in [analysis_audit, hypothesis_audit]]
    flags = []
    for segment in analysis['segments']:
        if segment['kind'] == 'hook' and segment['start'] >= 2:
            flags.append({'kind': 'hook_outside_initial_two_seconds', 'frame_index': segment['frame_index']})
        if segment['kind'] == 'cta' and 'licensed under' in segment['text'].lower():
            flags.append({'kind': 'license_credit_classified_as_cta', 'frame_index': segment['frame_index']})
    report = {'protocol': 'gemini-offline-review-v1', 'post_hoc': True,
        'network_requests': 0, 'additional_cost_usd': 0,
        'original_status': summary['status'], 'original_schema_accepted': summary['schema_accepted'],
        'original_hypothesis_accepted_on_replay': original_accepted,
        'revised_hypothesis_accepted_on_replay': True,
        'correction': 'Only exact baseline preservation text is exempt from the prose digit ban; generated prose remains checked.',
        'evaluation': run.original.evaluate(analysis, hypotheses, baseline, freeze),
        'usage_from_both_raw_responses': {k: sum(u[k] for u in usage)
            for k in ['promptTokenCount', 'candidatesTokenCount', 'totalTokenCount']},
        'expected_free_tier_cost_usd': 0, 'billed_cost_usd': None,
        'semantic_review_flags': flags,
        'flags_are': 'Post-hoc consistency warnings, not human factual accuracy labels.',
        'original_summary_sha256': run.guard._sha(directory / 'summary.json'),
        'review_runtime_sha256': run.guard._sha(Path(__file__)),
        'limitations': summary['limitations'] + [
            'Offline correction was designed after observing this failure; it is not a prospective success.',
            'An accepted response can still contain semantic errors. No engagement benefit was measured.']}
    output = ROOT / 'artifacts/verification/gemini_offline_review.json'
    run.guard._write(output, report)
    return report


if __name__ == '__main__':
    print(json.dumps(review(), indent=2))
