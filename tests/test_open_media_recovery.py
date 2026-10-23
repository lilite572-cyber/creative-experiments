import json
import unittest
from unittest.mock import patch
import httpx
import test_open_media_check as base
import recover_open_media_check as recovery
from provider_diagnostics import DiagnosticTransport


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        base.OpenMediaCheckTests.setUp(self)
        self.stack.enter_context(patch.object(recovery, 'ROOT', self.root))
        self.ledger.mkdir()
        initial = {'attempts': [{'operation_id': 'analysis', 'status': 'unknown', 'reservation_cents': 10}],
                   'reserved_cents': 10, 'limit_cents': 500, 'halted': True}
        for name, value in [('ledger.json', initial), ('origin.json', {}),
                            ('attempt-analysis.json', {'test_only': True}), ('summary.json', {})]:
            recovery.guard._write(self.ledger / name, value)
        self.original_bytes = (self.ledger / 'ledger.json').read_bytes()
        digest = recovery.guard._sha(self.ledger / 'ledger.json')
        self.stack.enter_context(patch.object(recovery, 'EXPECTED_LEDGER', digest))
        plan = {'runtime': {}, 'prior_files': {name: recovery.guard._sha(self.ledger / name)
                                              for name in recovery.FILES}}
        self.plan = self.root / 'plan.json'
        self.plan.write_text(json.dumps(plan))
        self.stack.enter_context(patch.object(recovery, 'PLAN', self.plan))
        self.stack.enter_context(patch.object(recovery, 'check_plan', return_value=(plan, self.freeze, self.frames)))

    def tearDown(self):
        base.OpenMediaCheckTests.tearDown(self)

    def transport(self, request):
        return base.OpenMediaCheckTests.transport(self, request)

    def run_recovery(self, transport=None):
        return recovery.execute(key='sk-test-fixture-never-real', availability={'available': True},
                                transport_factory=lambda key: transport or self.transport)

    def test_prior_unknown_is_retained_and_new_attempts_reserved(self):
        report = self.run_recovery()
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['new_attempts'], 2)
        self.assertEqual(report['total_reserved_usd'], .3)
        self.assertIsNone(report['total_usage_cost_usd'])
        self.assertAlmostEqual(report['new_usage_cost_estimate_usd'], .00112)
        ledger = json.loads((self.ledger / 'ledger.json').read_text())
        self.assertEqual(ledger['attempts'][0]['status'], 'unknown')
        self.assertTrue(ledger['halted'])
        self.assertEqual((self.ledger / 'recovery-v1/prior-ledger.json').read_bytes(), self.original_bytes)
        with self.assertRaises(ValueError):
            self.run_recovery()
        self.assertEqual(len(self.calls), 2)

    def test_changed_prior_evidence_cannot_start_recovery(self):
        (self.ledger / 'attempt-analysis.json').write_text('{}')
        with self.assertRaises(ValueError):
            self.run_recovery()
        self.assertEqual(self.calls, [])

    def test_timeout_stops_and_preserves_both_reservations(self):
        def fail(request):
            self.calls.append(request)
            raise TimeoutError('synthetic transport failure')
        report = self.run_recovery(fail)
        self.assertEqual(report['status'], 'halted')
        self.assertEqual(report['total_reserved_usd'], .2)
        self.assertEqual(report['new_attempts'], 1)
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(ValueError):
            self.run_recovery()

    def test_unavailable_metadata_does_not_mutate_prior_ledger(self):
        result = recovery.execute(key='sk-test-only', availability={'available': False})
        self.assertEqual(result['new_inference_requests'], 0)
        self.assertEqual((self.ledger / 'ledger.json').read_bytes(), self.original_bytes)


class TransportDiagnosticsTests(unittest.TestCase):
    def make(self, handler):
        def factory(**kwargs):
            return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)
        return DiagnosticTransport('sk-local-secret-value', factory)

    def test_http_error_retains_status_code_param_and_redacts_secret(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(400, json={'error': {'code': 'invalid_json_schema',
                'param': 'text.format.schema', 'message': 'Rejected sk-local-secret-value Bearer unrelated-token'}})
        transport = self.make(handler)
        with self.assertRaisesRegex(ValueError, 'HTTP 400'):
            transport({})
        data = json.dumps(transport.telemetry)
        self.assertEqual(transport.telemetry['http_status'], 400)
        self.assertIn('invalid_json_schema', data)
        self.assertNotIn('sk-local-secret-value', data)
        self.assertNotIn('unrelated-token', data)
        self.assertEqual(len(calls), 1)

    def test_network_exception_type_is_retained_without_request_headers(self):
        def fail(request):
            raise httpx.ConnectError('secret-bearing underlying detail', request=request)
        transport = self.make(fail)
        with self.assertRaisesRegex(ValueError, 'ConnectError'):
            transport({})
        self.assertEqual(transport.telemetry['failure_kind'], 'ConnectError')
        self.assertNotIn('secret-bearing', json.dumps(transport.telemetry))

    def test_invalid_json_retains_http_status(self):
        transport = self.make(lambda request: httpx.Response(502, content=b'not json'))
        with self.assertRaises(ValueError):
            transport({})
        self.assertEqual(transport.telemetry['http_status'], 502)
        self.assertEqual(transport.telemetry['failure_kind'], 'invalid_json_response')

    def test_success_retains_response_usage(self):
        transport = self.make(lambda request: httpx.Response(200, json={'usage': {'input_tokens': 12}}))
        self.assertEqual(transport({})['usage']['input_tokens'], 12)


if __name__ == '__main__':
    unittest.main()
