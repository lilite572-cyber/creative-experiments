import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import import_gemini_evidence as importer
from app import db


class EvidenceImportTests(unittest.TestCase):
    def test_semantic_flags_do_not_change_saved_model_result(self):
        original = {'hook_category': 'preparation', 'limitations': [], 'segments': [], 'model': 'gemini'}
        before = copy.deepcopy(original)
        result = importer.imported_analysis(original, {'semantic_review_flags': []})
        self.assertEqual(original, before)
        self.assertEqual(result['mode'], 'gemini_import')
        self.assertEqual(result['hook_category'], 'unknown')
        self.assertEqual(result['raw_model_hook_category'], 'preparation')

    def test_scoped_import_is_idempotent_and_cannot_change_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            packet = root / 'packet'
            packet.mkdir()
            (packet / 'source.mp4').write_bytes(b'fixture bytes, not real video')
            analysis = {'hook_category': 'preparation', 'limitations': [], 'segments': [],
                'model': 'gemini-test', 'prompt_version': 'test'}
            freeze = {'source': {'license': 'test-only'}, 'measured': {'duration': 1}}
            report = {'semantic_review_flags': [], 'original_summary_sha256': 'test-only'}
            with patch.object(db, 'ROOT', root / 'data'), \
                    patch.object(importer.review, 'review', return_value=report), \
                    patch.object(importer.review.run.original, 'PACKET', packet), \
                    patch.object(importer.review.run.original, 'check_packet', return_value=(freeze, [])), \
                    patch.object(importer.review.run.guard, '_json', return_value={'result': analysis}):
                db.init()
                with db.connect() as c:
                    c.execute('INSERT INTO users VALUES(?,?,?)', ('one', 'one@example.test', 'test'))
                    c.execute('INSERT INTO users VALUES(?,?,?)', ('two', 'two@example.test', 'test'))
                self.assertEqual(importer.load('one@example.test')['status'], 'imported')
                self.assertEqual(importer.load('one@example.test')['status'], 'already_imported')
                with self.assertRaisesRegex(ValueError, 'different owner'):
                    importer.load('two@example.test')
                with db.connect() as c:
                    self.assertEqual(len(db.rows(c, importer.WORKSPACE, 'video')), 1)
                    self.assertEqual(db.rows(c, importer.WORKSPACE, 'metric'), [])
                    self.assertFalse(db.rows(c, importer.WORKSPACE, 'video')[0]['synthetic'])


if __name__ == '__main__':
    unittest.main()
