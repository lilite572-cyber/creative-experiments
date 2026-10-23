import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from review_gemini_run import validate_with_fixed_preservation


class OfflineReviewTests(unittest.TestCase):
    def setUp(self):
        self.baseline = [{'id': 'known', 'preserve': ['Video after second 2'],
            'threshold_pp': 5, 'sources': [{'video_id': 'v', 'start': 0, 'end': 2}]}]
        self.result = {'recommendations': [{'candidate_id': 'known',
            'preserve': ['Video after second 2'], 'hypothesis': 'Try another opening.',
            'change': 'Show the product in use.', 'explanation': 'Exploratory only.'}]}

    def test_exact_baseline_digits_retained_without_changing_sources_or_inputs(self):
        before = copy.deepcopy(self.result)
        output = validate_with_fixed_preservation(self.result, self.baseline)[0]
        self.assertEqual(output['preserve'], self.baseline[0]['preserve'])
        self.assertEqual(output['sources'], self.baseline[0]['sources'])
        self.assertEqual(output['threshold_pp'], 5)
        self.assertEqual(self.result, before)

    def test_changed_preservation_rejected(self):
        self.result['recommendations'][0]['preserve'] = ['Video after second 3']
        with self.assertRaises(ValueError):
            validate_with_fixed_preservation(self.result, self.baseline)

    def test_generated_numeric_claims_still_rejected(self):
        self.result['recommendations'][0]['hypothesis'] = 'Expect 20% improvement.'
        with self.assertRaises(ValueError):
            validate_with_fixed_preservation(self.result, self.baseline)

    def test_unknown_or_duplicate_candidate_rejected(self):
        self.result['recommendations'][0]['candidate_id'] = 'invented'
        with self.assertRaises(ValueError):
            validate_with_fixed_preservation(self.result, self.baseline)
        self.result['recommendations'][0]['candidate_id'] = 'known'
        self.result['recommendations'] *= 2
        with self.assertRaises(ValueError):
            validate_with_fixed_preservation(self.result, self.baseline)
