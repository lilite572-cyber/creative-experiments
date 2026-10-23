import contextlib
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_gemini_check as runner
from app import gemini_provider as gemini


def response(data):
    return {'modelVersion': gemini.MODEL, 'candidates': [{
        'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(data)}]}}],
        'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 100, 'totalTokenCount': 200}}


class GeminiCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.stack = contextlib.ExitStack()
        self.packet = self.root / 'packet'
        self.packet.mkdir()
        (self.packet / 'freeze.json').write_text('{}')
        frame = self.packet / 'frame.jpg'
        Image.new('RGB', (32, 32), 'blue').save(frame)
        self.frames = [{'path': frame, 'index': 0, 'time': 0.0}]
        self.freeze = {'source': {'source_id': runner.original.SID},
            'measured': {'duration': 1.0, 'fps': 24.0, 'has_audio': False},
            'frames': [{'index': 0, 'time': 0.0}]}
        self.prior = self.root / 'openai'
        self.prior.mkdir()
        (self.prior / 'ledger.json').write_text('{"halted":true,"reserved_cents":20}')
        for name in runner.RUNTIME:
            path = self.root / name
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_text('frozen test fixture')
        self.private = self.root / 'data/private/gemini-open-media-v1'
        self.key_path = self.root / 'data/private/gemini_api_key'
        for obj, name, value in [(runner, 'ROOT', self.root), (runner, 'PRIVATE', self.private),
                (runner, 'KEY', self.key_path), (runner.original, 'PACKET', self.packet),
                (runner.guard, 'LEDGER_ROOT', self.prior)]:
            self.stack.enter_context(patch.object(obj, name, value))
        self.stack.enter_context(patch.object(runner.original, 'check_packet', return_value=(self.freeze, self.frames)))
        runner.prepare()
        self.key = 'AIza' + 'x' * 35
        self.key_path.write_text(self.key)
        self.key_path.chmod(0o600)
        self.auth = {'provider': 'gemini', 'model': gemini.MODEL, 'budget_usd': 0,
            'free_tier_confirmed_by_owner': True, 'public_media_processing_confirmed': True,
            'key_sha256': runner.key_digest(self.key)}
        runner.guard._write(self.private / 'authorization.json', self.auth)
        self.calls = []

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def factory(self, key):
        owner = self
        class Fake:
            telemetry = {'http_status': 200}
            def __call__(self, payload):
                owner.calls.append(payload)
                if len(owner.calls) == 1:
                    return response({'hook_category': 'unknown', 'observations': [
                        {'frame_index': 0, 'kind': 'scene', 'text': 'Test fixture.'}]})
                baseline = json.loads(payload['contents'][0]['parts'][1]['text'])
                return response({'recommendations': [{'candidate_id': baseline[0]['id'],
                    'hypothesis': 'An alternative opening might affect retention.',
                    'change': 'Try another opening.', 'preserve': ['Keep the main body.'],
                    'explanation': 'Exploratory only; no publication data.'}]})
        return Fake()

    def test_full_path_preserves_prior_evidence_and_blocks_replay(self):
        before = (self.prior / 'ledger.json').read_bytes()
        report = runner.execute(self.factory)
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['schema_accepted'], 2)
        self.assertTrue(report['evaluation']['programmatic_fields_preserved'])
        self.assertEqual(report['evaluation']['human_quality_assessment'], 'not_performed')
        self.assertIsNone(report['billed_cost_usd'])
        self.assertEqual((self.prior / 'ledger.json').read_bytes(), before)
        self.assertNotIn(self.key, json.dumps(report))
        self.assertNotIn('inlineData', json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'already exists'):
            runner.execute(self.factory)
        self.assertEqual(len(self.calls), 2)

    def test_no_free_tier_confirmation_no_request(self):
        self.auth['free_tier_confirmed_by_owner'] = False
        runner.guard._write(self.private / 'authorization.json', self.auth)
        with self.assertRaisesRegex(ValueError, 'authorization'):
            runner.execute(self.factory)
        self.assertFalse(self.calls)
        self.assertFalse((self.private / 'run').exists())

    def test_key_change_and_insecure_permissions_blocked(self):
        self.key_path.chmod(0o644)
        with self.assertRaises(ValueError):
            runner.execute(self.factory)
        self.key_path.chmod(0o600)
        self.key_path.write_text('AIza' + 'y' * 35)
        with self.assertRaises(ValueError):
            runner.execute(self.factory)
        self.assertFalse(self.calls)

    def test_frozen_runtime_and_prior_ledger_tamper_rejected(self):
        path = self.root / runner.RUNTIME[0]
        before = path.read_text()
        path.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'runtime'):
            runner.check()
        path.write_text(before)
        (self.prior / 'ledger.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Prior source'):
            runner.check()

    def test_timeout_blocks_second_call_and_replay(self):
        class Failed:
            telemetry = {'http_status': None}
            def __call__(self, payload):
                raise gemini.Error('Timeout test')
        report = runner.execute(lambda key: Failed())
        self.assertEqual(report['status'], 'halted')
        self.assertEqual(report['attempted'], 1)
        self.assertEqual(report['attempts'][0]['status'], 'unknown')
        with self.assertRaises(ValueError):
            runner.execute(self.factory)

    def test_invalid_evidence_reference(self):
        with self.assertRaisesRegex(ValueError, 'frame reference'):
            gemini.validate_analysis({'hook_category': 'unknown', 'observations': [
                {'frame_index': 999, 'kind': 'scene', 'text': 'Wrong frame'}]}, self.freeze['measured'], self.frames)

    def test_incomplete_wrong_model_missing_usage(self):
        good = response({'test': True})
        for alteration in ('truncated', 'model', 'usage', 'duplicate'):
            value = copy.deepcopy(good)
            if alteration == 'truncated':
                value['candidates'][0]['finishReason'] = 'MAX_TOKENS'
            elif alteration == 'model':
                value['modelVersion'] = 'unexpected'
            elif alteration == 'usage':
                value.pop('usageMetadata')
            else:
                value['candidates'][0]['content']['parts'][0]['text'] = '{"x":1,"x":2}'
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                gemini.parse(value)

    def test_unknown_candidate_and_invented_numbers_rejected(self):
        baseline = [{'id': 'known', 'sources': [{'video_id': 'v'}]}]
        item = {'candidate_id': 'unknown', 'hypothesis': 'Try something.', 'change': 'Opening.',
            'preserve': ['Body.'], 'explanation': 'Exploration.'}
        with self.assertRaises(ValueError):
            gemini.validate_hypotheses({'recommendations': [item]}, baseline)
        item.update(candidate_id='known', hypothesis='Improves by 20%.')
        with self.assertRaises(ValueError):
            gemini.validate_hypotheses({'recommendations': [item]}, baseline)

    def test_http_429_no_retry_and_secret_redacted(self):
        calls = []
        def handler(req):
            calls.append(req)
            self.assertEqual(req.headers['x-goog-api-key'], self.key)
            self.assertNotIn(self.key, str(req.url))
            return httpx.Response(429, json={'error': {'code': 429, 'message': self.key}})
        transport = gemini.Transport(self.key, lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs))
        with self.assertRaisesRegex(ValueError, '429'):
            transport({'test': True})
        self.assertEqual(len(calls), 1)
        self.assertNotIn(self.key, json.dumps(transport.telemetry))

    def test_request_uses_native_images_and_no_tools(self):
        value = gemini.analysis_request(self.freeze['measured'], self.frames)
        self.assertEqual(len(value['contents'][0]['parts']), 3)
        self.assertEqual(value['contents'][0]['parts'][2]['inlineData']['mimeType'], 'image/jpeg')
        self.assertNotIn('tools', value)
        self.assertEqual(value['generationConfig']['maxOutputTokens'], 4096)


if __name__ == '__main__':
    unittest.main()
