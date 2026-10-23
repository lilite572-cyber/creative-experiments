import contextlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_open_media_check as runner


class OpenMediaCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.packet = self.root / 'packet'
        self.packet.mkdir()
        (self.packet / 'freeze.json').write_text('{}')
        frame = self.packet / 'frame.jpg'
        Image.new('RGB', (32, 32), 'blue').save(frame)
        self.frames = [{'path': frame, 'index': 0, 'time': 0.0}]
        self.freeze = {'protocol': 'test-only', 'source': {'source_id': runner.SID},
                       'measured': {'duration': 1.0, 'fps': 24.0, 'has_audio': False},
                       'frames': [{'index': 0, 'time': 0.0}], 'code': {},
                       'files': {'source.mp4': 'test-fixture'}}
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.object(runner, 'ROOT', self.root))
        self.stack.enter_context(patch.object(runner, 'PACKET', self.packet))
        self.ledger = self.root / 'ledger'
        self.stack.enter_context(patch.object(runner.guard, 'LEDGER_ROOT', self.ledger))
        self.stack.enter_context(patch.object(runner, 'check_packet', return_value=(self.freeze, self.frames)))
        self.calls = []

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def transport(self, request):
        self.calls.append(request)
        if request['text']['format']['name'] == 'video_observations':
            data = {'hook_category': 'unknown', 'observations': [
                {'frame_index': 0, 'kind': 'scene', 'text': 'Synthetic software-test fixture.'}]}
        else:
            candidates = json.loads(request['input'][1]['content'])
            data = {'recommendations': [{'candidate_id': candidates[0]['id'],
                    'hypothesis': 'An alternate opening might change retention.',
                    'change': 'Try a different opening.', 'preserve': ['Keep the remainder.'],
                    'explanation': 'No publication metrics; exploratory only.'}]}
        return {'model': runner.provider.MODEL, 'status': 'completed',
                'output': [{'content': [{'type': 'output_text', 'text': json.dumps(data)}]}],
                'usage': {'input_tokens': 1000, 'output_tokens': 100}}

    def run_check(self, transport=None, available=True):
        return runner.execute(transport=transport or self.transport,
                              key='sk-test-fixture-never-real', availability={'available': available})

    def test_success_preserves_baseline_and_does_not_claim_human_accuracy(self):
        result = self.run_check()
        self.assertEqual(result['attempted'], 2)
        self.assertEqual(result['reserved_usd'], 0.2)
        self.assertAlmostEqual(result['usage_cost_estimate_usd'], 0.00112)
        self.assertTrue(result['evaluation']['programmatic_fields_preserved'])
        self.assertEqual(result['evaluation']['human_quality_assessment'], 'not_performed')
        self.assertEqual(result['evaluation']['hypothesis_references'], {'total': 1, 'valid': 1})
        report = (self.root / 'artifacts/verification/open_media_integration.json').read_text()
        self.assertNotIn('data:image', report)
        self.assertNotIn('sk-test', report)
        with self.assertRaisesRegex(ValueError, 'already contains'):
            self.run_check()
        self.assertEqual(len(self.calls), 2)

    def test_previous_original_pilot_ledger_cannot_be_reset(self):
        self.ledger.mkdir()
        (self.ledger / 'ledger.json').write_text('{"previous":true}')
        with self.assertRaisesRegex(ValueError, 'already contains'):
            self.run_check()
        self.assertFalse(self.calls)

    def test_unavailable_model_sends_no_inference_or_reservation(self):
        self.assertEqual(self.run_check(available=False)['status'], 'provider_unavailable')
        self.assertFalse(self.calls)
        self.assertFalse((self.ledger / 'ledger.json').exists())

    def test_unknown_outcome_stops_and_blocks_replay(self):
        def fail(request):
            self.calls.append(request)
            raise TimeoutError('test only')
        result = self.run_check(fail)
        self.assertEqual(result['attempted'], 1)
        self.assertIsNone(result['usage_cost_estimate_usd'])
        self.assertEqual(result['operations'][0]['status'], 'unknown')
        with self.assertRaises(ValueError):
            self.run_check()
        self.assertEqual(len(self.calls), 1)

    def test_missing_usage_stops_before_second_call(self):
        def missing(request):
            response = self.transport(request)
            response.pop('usage')
            return response
        result = self.run_check(missing)
        self.assertEqual(result['status'], 'halted')
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(result['usage_cost_estimate_usd'])

    def test_bad_evidence_reference_is_rejected(self):
        def invalid(request):
            response = self.transport(request)
            data = json.loads(response['output'][0]['content'][0]['text'])
            data['observations'][0]['frame_index'] = 999
            response['output'][0]['content'][0]['text'] = json.dumps(data)
            return response
        result = self.run_check(invalid)
        self.assertEqual(result['schema_accepted'], 0)
        self.assertEqual(len(self.calls), 1)

    def test_usage_limits(self):
        self.assertFalse(runner.usage_ok({'input_tokens': 20001, 'output_tokens': 1, 'cost_usd': .01}))
        self.assertFalse(runner.usage_ok({'input_tokens': 1, 'output_tokens': 1201, 'cost_usd': .01}))
        self.assertFalse(runner.usage_ok({'input_tokens': 1, 'output_tokens': 1, 'cost_usd': float('nan')}))


if __name__ == '__main__':
    unittest.main()
