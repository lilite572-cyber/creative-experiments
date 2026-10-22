import csv
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
prep = load('pilot_prepare_for_runner', 'prepare_live_pilot.py')
runner = load('pilot_runner_under_test', 'run_live_pilot.py')
from app.media import make_demo
from app.provider import MODEL
FAKE = 'sk-local-unit-test-no-real-provider-key'

class LivePilotRunnerTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fixture_dir = tempfile.TemporaryDirectory()
        cls.fixture = Path(cls.fixture_dir.name) / 'fixture.mp4'
        make_demo(cls.fixture, duration=1)

    @classmethod
    def tearDownClass(cls):
        cls.fixture_dir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.media = self.root / 'media'
        self.media.mkdir()
        (self.media / 'fixture.mp4').write_bytes(self.fixture.read_bytes())
        manifest = self.root / 'manifest.csv'
        with manifest.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=prep.COLUMNS)
            writer.writeheader()
            writer.writerow({'source_id': 'test-source', 'path': 'fixture.mp4', 'source_url': 'https://example.org/fixture', 'credit': 'Unit test', 'rights_url': 'https://example.org/license', 'rights_note': 'Authored synthetic fixture for offline tests, not real human source confirmation', 'distribution_allowed': 'false'})
        self.packet = self.root / 'packet'
        prep.prepare(manifest, self.media, self.packet)
        self.ledger = self.root / 'ledger'
        self.patch_ledger = patch.object(runner, 'LEDGER_ROOT', self.ledger)
        self.patch_ledger.start()
        self.patch_env = patch.dict(os.environ, {'OPENAI_API_KEY': FAKE})
        self.patch_env.start()
        self.calls = []

    def tearDown(self):
        self.patch_env.stop()
        self.patch_ledger.stop()
        self.temp.cleanup()

    def human_fixture(self, independent=False):
        confirmation = {'reviewer': 'synthetic-test-fixture-not-a-human-study', 'sources': [{'source_id': 'test-source', 'independent_original_recording_confirmed': independent, 'lawful_api_analysis_confirmed': True, 'rights_reference_reviewed': True, 'notes': 'Test fixture; recording independence intentionally unconfirmed.'}]}
        (self.packet / 'source_confirmation.json').write_text(json.dumps(confirmation))
        path = self.packet / 'human_review.csv'
        with path.open() as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            row.update(hook_category='unknown', reviewer='synthetic-unit-test', notes='Authored uncertainty label for offline software test only.')
        with path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=prep.REVIEW_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def transport(self, request):
        self.calls.append(request)
        if request['text']['format']['name'] == 'video_observations':
            result = {'hook_category': 'unknown', 'observations': [{'frame_index': 0, 'kind': 'scene', 'text': 'Fixture scene'}]}
        else:
            candidates = json.loads(request['input'][1]['content'])
            result = {'recommendations': [{'candidate_id': candidates[0]['id'], 'hypothesis': 'A different opening may change retention; this is exploratory.', 'change': 'Replace the opening with the product in use.', 'preserve': ['Keep the remainder and original audio.'], 'explanation': 'No publication statistics are available.'}]}
        return {'id': 'fake-' + str(len(self.calls)), 'status': 'completed', 'model': MODEL, 'output': [{'content': [{'type': 'output_text', 'text': json.dumps(result)}]}], 'usage': {'input_tokens': 1000, 'output_tokens': 100}}

    def test_blank_human_gates_before_key_or_ledger(self):
        with patch.object(runner, '_key', side_effect=AssertionError('Key must not be read')):
            with self.assertRaisesRegex(ValueError, 'reviewer'):
                runner.run(self.packet, transport=self.transport)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.ledger.exists())

    def test_rights_and_human_review_each_required(self):
        self.human_fixture()
        path = self.packet / 'source_confirmation.json'
        value = json.loads(path.read_text())
        value['sources'][0]['lawful_api_analysis_confirmed'] = False
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'rights'):
            runner.check_packet(self.packet)
        self.human_fixture()
        path = self.packet / 'human_review.csv'
        text = path.read_text().replace('synthetic-unit-test', '')
        path.write_text(text)
        with self.assertRaisesRegex(ValueError, 'reviewer'):
            runner.check_packet(self.packet)

    def test_related_recordings_allowed_but_not_claimed_independent(self):
        self.human_fixture(False)
        with patch.object(runner, '_key', side_effect=AssertionError('No key in check-only')):
            report = runner.check_packet(self.packet)
        self.assertEqual(report['independence'], 'not_established_integration_only')
        self.assertFalse(self.ledger.exists())

    def test_success_resumption_no_duplicate_requests_and_no_secret_leak(self):
        self.human_fixture()
        first = runner.run(self.packet, transport=self.transport)
        self.assertEqual(first['attempts'], 4)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(first['reserved_usd'], 0.4)
        resumed = runner.run(self.packet, transport=self.transport)
        self.assertEqual(resumed['attempts'], 4)
        self.assertEqual(len(self.calls), 4)
        for path in self.ledger.glob('*.json'):
            self.assertNotIn(FAKE, path.read_text())

    def test_changed_evidence_never_sends(self):
        self.human_fixture()
        freeze = json.loads((self.packet / 'freeze.json').read_text())
        path = self.packet / freeze['sources'][0]['frames'][0]['path']
        path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'frame changed'):
            runner.run(self.packet, transport=self.transport)
        self.assertEqual(self.calls, [])

    def test_changed_labels_after_execution_block_resume(self):
        self.human_fixture()
        runner.run(self.packet, transport=self.transport)
        path = self.packet / 'human_review.csv'
        path.write_text(path.read_text().replace('Authored uncertainty', 'Changed uncertainty'))
        with self.assertRaisesRegex(ValueError, 'immutable packet|changed'):
            runner.run(self.packet, transport=self.transport)
        self.assertEqual(len(self.calls), 4)

    def test_unknown_outcome_reserves_before_call_and_blocks_resume(self):
        self.human_fixture()

        def timed_out(request):
            ledger = json.loads((self.ledger / 'ledger.json').read_text())
            self.assertEqual(ledger['reserved_cents'], 10)
            self.assertEqual(ledger['attempts'][0]['status'], 'pending')
            raise TimeoutError('unknown')
        with self.assertRaisesRegex(ValueError, 'halted'):
            runner.run(self.packet, transport=timed_out)
        with self.assertRaisesRegex(ValueError, 'unknown outcome'):
            runner.run(self.packet, transport=self.transport)
        self.assertEqual(self.calls, [])

    def test_pending_interruption_blocks_resume(self):
        self.human_fixture()
        with self.assertRaises(KeyboardInterrupt):
            runner.run(self.packet, transport=lambda r: (_ for _ in ()).throw(KeyboardInterrupt()))
        ledger = json.loads((self.ledger / 'ledger.json').read_text())
        self.assertEqual(ledger['attempts'][0]['status'], 'pending')
        with self.assertRaisesRegex(ValueError, 'unknown outcome'):
            runner.run(self.packet, transport=self.transport)

    def test_large_cost_halts_after_one_call(self):
        self.human_fixture()

        def costly(request):
            response = self.transport(request)
            response['usage']['input_tokens'] = 1000000
            return response
        with self.assertRaisesRegex(ValueError, 'halted'):
            runner.run(self.packet, transport=costly)
        self.assertEqual(len(self.calls), 1)

    def test_lock_blocks_concurrent_runner(self):
        self.human_fixture()
        self.ledger.mkdir()
        lock = os.open(self.ledger / 'execution.lock', os.O_RDWR | os.O_CREAT, 384)
        try:
            runner.fcntl.flock(lock, runner.fcntl.LOCK_EX | runner.fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, 'exclusive process lock'):
                runner.run(self.packet, transport=self.transport)
        finally:
            os.close(lock)
        self.assertEqual(self.calls, [])

    def test_model_and_input_cap(self):
        with self.assertRaisesRegex(ValueError, 'model'):
            runner._request_cap({'model': 'unapproved', 'max_output_tokens': 1200, 'store': False})
        with self.assertRaisesRegex(ValueError, 'input allowance'):
            runner._request_cap({'model': MODEL, 'max_output_tokens': 1200, 'store': False, 'input': [{'content': 'x' * 12001}]})

    def test_missing_ledger_never_resets_budget(self):
        self.human_fixture()
        runner.run(self.packet, transport=self.transport)
        (self.ledger / 'ledger.json').unlink()
        with self.assertRaisesRegex(ValueError, 'deleted ledger'):
            runner.run(self.packet, transport=self.transport)
        self.assertEqual(len(self.calls), 4)

    def test_uncertain_blank_labels_allowed_and_excluded(self):
        self.human_fixture()
        path = self.packet / 'human_review.csv'
        path.write_text(path.read_text().replace('unknown,', ','))
        self.assertEqual(runner.check_packet(self.packet)['blank_hook_rows_excluded'], 8)
        report = runner.run(self.packet, transport=self.transport)
        evaluation = report['evaluation']
        self.assertEqual(evaluation['human_hook_comparison']['comparisons'], 0)
        self.assertIsNone(evaluation['human_hook_comparison']['accuracy'])
        self.assertEqual(evaluation['analysis_references'], {'valid': 2, 'total': 2})
        self.assertEqual(evaluation['repeat_consistency']['agreeing_sources'], 1)
        self.assertEqual(json.loads((self.ledger / 'summary.json').read_text()), report)

    def test_actual_available_labels_scored_separately_from_baseline(self):
        self.human_fixture()
        path = self.packet / 'human_review.csv'
        path.write_text(path.read_text().replace('unknown,', 'preparation,'))

        def correct(request):
            response = self.transport(request)
            if request['text']['format']['name'] == 'video_observations':
                text = response['output'][0]['content'][0]
                text['text'] = text['text'].replace('unknown', 'preparation')
            return response
        report = runner.run(self.packet, transport=correct)
        checks = report['evaluation']['human_hook_comparison']
        self.assertEqual((checks['matched'], checks['comparisons']), (2, 2))
        self.assertEqual(checks['baseline']['matched'], 0)
        self.assertEqual(len(checks['rows']), 1)

    def test_raw_response_secrets_are_redacted(self):
        self.human_fixture()

        def echo(request):
            response = self.transport(request)
            response['diagnostic_echo'] = FAKE
            return response
        runner.run(self.packet, transport=echo)
        for path in self.ledger.glob('*.json'):
            self.assertNotIn(FAKE, path.read_text())
        self.assertIn('[redacted]', (self.ledger / 'attempt-001.json').read_text())

    def test_ledger_over_budget_or_unaccounted_reservation_is_rejected(self):
        binding = {'fixture': True}
        ledger = {'binding': binding, 'attempts': [], 'reserved_cents': 10, 'limit_cents': 500, 'halted': False}
        with self.assertRaisesRegex(ValueError, 'spending ledger'):
            runner._ledger_check(ledger, binding)
        ledger['attempts'] = [{'operation_id': str(i), 'status': 'succeeded'} for i in range(51)]
        ledger['reserved_cents'] = 510
        with self.assertRaisesRegex(ValueError, 'spending ledger'):
            runner._ledger_check(ledger, binding)

    def test_missing_usage_halts_without_next_request(self):
        self.human_fixture()

        def no_usage(request):
            response = self.transport(request)
            del response['usage']
            return response
        with self.assertRaisesRegex(ValueError, 'halted'):
            runner.run(self.packet, transport=no_usage)
        self.assertEqual(len(self.calls), 1)

    def test_invalid_model_reference_halts_after_one_request(self):
        self.human_fixture()

        def bad_reference(request):
            response = self.transport(request)
            text = response['output'][0]['content'][0]
            text['text'] = text['text'].replace('"frame_index": 0', '"frame_index": 99')
            return response
        with self.assertRaisesRegex(ValueError, 'halted'):
            runner.run(self.packet, transport=bad_reference)
        self.assertEqual(len(self.calls), 1)

    def test_changed_baseline_dependency_blocks_resume(self):
        self.human_fixture()
        runner.run(self.packet, transport=self.transport)
        original_sha = runner._sha
        def changed_sha(path):
            if path == ROOT / 'app/research.py':
                return 'changed-baseline-code'
            return original_sha(path)
        with patch.object(runner, '_sha', side_effect=changed_sha):
            with self.assertRaisesRegex(ValueError, 'immutable packet|changed'):
                runner.run(self.packet, transport=self.transport)
        self.assertEqual(len(self.calls), 4)

    def test_output_usage_over_cap_halts_after_one_call(self):
        self.human_fixture()
        def excessive_output(request):
            response = self.transport(request)
            response['usage']['output_tokens'] = 1201
            return response
        with self.assertRaisesRegex(ValueError, 'halted'):
            runner.run(self.packet, transport=excessive_output)
        self.assertEqual(len(self.calls), 1)

if __name__ == '__main__':
    unittest.main()
