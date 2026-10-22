import csv
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_live_pilot", ROOT / "scripts/prepare_live_pilot.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from app.media import make_demo


class LivePilotPreparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.media = cls.base / 'media'
        cls.media.mkdir()
        make_demo(cls.media / 'fixture.mp4', duration=1)
        cls.config = json.loads((ROOT / 'configs/live_pilot_v1.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def manifest(self, name='manifest.csv', **changes):
        row = {'source_id':'fixture-a','path':'fixture.mp4','source_url':'https://example.org/owned-fixture','credit':'Test fixture creator','rights_url':'https://example.org/fixture-rights','rights_note':'Synthetic local test fixture only, not a natural study source.','distribution_allowed':'false'}
        row.update(changes)
        out = self.base / name
        with out.open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=module.COLUMNS);writer.writeheader();writer.writerow(row)
        return out

    def test_prepares_actual_frames_requests_and_blank_labels_without_network(self):
        output = self.base / 'valid-packet'
        with patch('app.provider._post_json', side_effect=AssertionError('Network prohibited')):
            result = module.prepare(self.manifest(), self.media, output)
        self.assertEqual(result['external_api_calls'],0)
        self.assertEqual(result['analysis_operations'],2)
        self.assertEqual(result['frames'],8)
        freeze=json.loads((output/'freeze.json').read_text())
        self.assertEqual(freeze['config']['model'],'gpt-4.1-mini-2025-04-14')
        source=freeze['sources'][0]
        self.assertEqual(source['source_sha256'],module.sha(output/source['media_path']))
        self.assertEqual(source['request_sha256'],module.sha(output/source['request_path']))
        self.assertTrue(all(module.sha(output/f['path'])==f['sha256'] for f in source['frames']))
        with (output/'human_review.csv').open() as handle:labels=list(csv.DictReader(handle))
        self.assertEqual(len(labels),8)
        for label in labels:
            self.assertTrue(all(label[field]=='' for field in module.REVIEW_COLUMNS[3:]))
        html=(output/'review.html').read_text()
        self.assertNotIn('hook_category=preparation',html)
        self.assertIn('No model predictions',html)
        confirmation=json.loads((output/'source_confirmation.json').read_text())
        self.assertIsNone(confirmation['sources'][0]['lawful_api_analysis_confirmed'])
        with self.assertRaisesRegex(ValueError,'already exists'):
            module.prepare(self.manifest(),self.media,output)

    def test_manifest_rejects_traversal_credentials_and_missing_rights(self):
        changes=[{'path':'../outside.mp4'},{'path':str(self.media/'fixture.mp4')},{'source_url':'https://secret@example.org/video'},{'rights_note':''},{'distribution_allowed':'yes'},{'rights_url':'http://example.org/license'},{'source_id':'../../escape'},{'source_url':'https://example.org/video?key=secret'}]
        for i,change in enumerate(changes):
            with self.subTest(change=change),self.assertRaises(ValueError):
                module.read_manifest(self.manifest(f'invalid-{i}.csv',**change),self.media,self.config)

    def test_symlink_escape_is_rejected(self):
        outside=self.base/'outside.mp4';outside.write_bytes((self.media/'fixture.mp4').read_bytes())
        link=self.media/'outside-link.mp4';link.symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'escapes'):
            module.read_manifest(self.manifest('link.csv',path='outside-link.mp4'),self.media,self.config)

    def test_byte_identical_sources_do_not_inflate_independence(self):
        duplicate=self.media/'duplicate.mp4';duplicate.write_bytes((self.media/'fixture.mp4').read_bytes())
        manifest=self.manifest('duplicates.csv')
        with manifest.open() as handle:row=list(csv.DictReader(handle))[0]
        row.update(source_id='fixture-b',path='duplicate.mp4')
        with manifest.open('a',newline='') as handle:csv.DictWriter(handle,fieldnames=module.COLUMNS).writerow(row)
        with self.assertRaisesRegex(ValueError,'independent'):
            module.read_manifest(manifest,self.media,self.config)

    def test_empty_and_invalid_media_never_publish_packet(self):
        empty=self.base/'empty.csv';empty.write_text(','.join(module.COLUMNS)+'\n')
        with self.assertRaisesRegex(ValueError,'empty'):
            module.prepare(empty,self.media,self.base/'empty-packet')
        invalid=self.media/'invalid.mp4';invalid.write_bytes(b'0000ftyp0000broken-media')
        output=self.base/'broken-packet'
        with self.assertRaises(ValueError):
            module.prepare(self.manifest('broken.csv',path='invalid.mp4'),self.media,output)
        self.assertFalse(output.exists())

    def test_budgets_include_all_repetitions_and_recovery(self):
        c=self.config
        self.assertEqual(c['maximum_analysis_attempts'],c['max_independent_sources']*c['analysis_repetitions_per_source'])
        self.assertEqual(c['maximum_total_attempts'],c['maximum_analysis_attempts']+c['maximum_hypothesis_attempts']+c['diagnostic_recovery_attempts'])
        self.assertEqual(c['maximum_total_attempts']*c['reservation_usd_per_attempt'],c['creative_experiments_reserved_limit_usd'])
        self.assertLessEqual(c['creative_experiments_reserved_limit_usd']+c['briefguard_separate_limit_usd'],c['combined_authorized_limit_usd'])
        actual=(c['planned_input_tokens_per_attempt']*c['input_usd_per_million']+c['max_output_tokens']*c['output_usd_per_million'])/1_000_000
        self.assertAlmostEqual(actual,c['planned_cost_usd_per_attempt'])
        self.assertAlmostEqual(actual*c['maximum_total_attempts'],c['planned_max_cost_usd'])
        self.assertEqual(c['automatic_retries'],0)


if __name__=='__main__':unittest.main()
