"""Evidence binding at the experiment HTTP boundary; no media or API calls."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import db
from app.main import app


class ExperimentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = patch.object(db, 'ROOT', Path(self.temp.name))
        root.start()
        self.addCleanup(root.stop)
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.client.post('/api/register', json={
            'email': 'evidence@example.test', 'password': 'evidence-test-only'})
        wid = self.client.post('/api/workspaces', json={'name': 'Evidence test'}).json()['id']
        self.base = f'/api/workspaces/{wid}'
        with db.connect() as c:
            for vid in ['a', 'b']:
                db.save(c, wid, 'video', {'id': vid, 'title': vid,
                    'duration': 8, 'synthetic': False, 'analysis': None})
        self.recommendation = self.client.get(self.base + '/recommendations').json()[0]

    def body(self, baseline_id):
        return {'title': 'Evidence binding', 'baseline_id': baseline_id,
            'recommendation_id': self.recommendation['id'],
            'hypothesis': self.recommendation['hypothesis'],
            'change': self.recommendation['change']}

    def test_mismatched_recommendation_rejected_without_saving_experiment(self):
        self.assertEqual(self.recommendation['baseline_id'], 'a')
        result = self.client.post(self.base + '/experiments', json=self.body('b'))
        self.assertEqual(result.status_code, 422)
        self.assertIn('must match', result.json()['detail'])
        self.assertEqual(self.client.get(self.base + '/experiments').json(), [])

    def test_matching_recommendation_keeps_original_source_snapshot(self):
        result = self.client.post(self.base + '/experiments', json=self.body('a'))
        self.assertEqual(result.status_code, 200, result.text)
        experiment = result.json()
        self.assertEqual(experiment['source_snapshot'], self.recommendation)
        self.assertEqual(experiment['baseline_id'], experiment['source_snapshot']['baseline_id'])

    def test_custom_experiment_without_recommendation_remains_supported(self):
        body = self.body('b')
        body.pop('recommendation_id')
        result = self.client.post(self.base + '/experiments', json=body)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIsNone(result.json()['source_snapshot'])
        self.assertEqual(result.json()['baseline_id'], 'b')
