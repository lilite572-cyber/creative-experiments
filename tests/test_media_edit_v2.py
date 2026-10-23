"""Generated-size regression and independent preservation checks for editor v2."""
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app import media
from app import media_edit_v2 as editor


class GeneratedMediaTests(unittest.TestCase):
    def test_generated_allowance_does_not_relax_input_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'generated.mp4'
            path.write_bytes(b'\x00\x00\x00\x18ftypisom' + b'x' * 2036)
            log = b'Duration: 00:00:01.00\nStream #0:0: Video: h264, yuv420p, 32x32, 24 fps\n'
            result = subprocess.CompletedProcess([], 0, stdout=b'', stderr=log)
            with patch.object(media, 'MAX_BYTES', 1024), \
                    patch.object(editor, 'MAX_GENERATED_BYTES', 8192), \
                    patch.object(editor, 'GENERATED_LIMIT_MARGIN', 256), \
                    patch.object(editor, '_run', return_value=result):
                with self.assertRaises(media.MediaError):
                    media.probe(path)
                metadata = editor.probe_generated(path)
                self.assertEqual(metadata['duration'], 1)
                self.assertEqual(metadata['fps'], 24)

    def test_at_or_near_generated_cap_rejected_before_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'generated.mp4'
            with patch.object(editor, 'MAX_GENERATED_BYTES', 8192), \
                    patch.object(editor, 'GENERATED_LIMIT_MARGIN', 256), \
                    patch.object(editor, '_run') as decode:
                for size in [8192 - 256, 8192, 8200]:
                    path.write_bytes(b'\x00\x00\x00\x18ftypisom' + b'x' * (size - 12))
                    with self.subTest(size=size), self.assertRaises(media.MediaError):
                        editor.probe_generated(path)
                decode.assert_not_called()


class EditorPreservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'source.mp4'
        cls.alternate = cls.root / 'alternate.mp4'
        media.make_demo(cls.source, 'packaging', 3)
        media.make_demo(cls.alternate, 'preparation', 2)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_edit_keeps_pixels_audio_timing_and_bounds_both_generated_files(self):
        source = self.root / 'audio.mp4'
        out = self.root / 'edited.mp4'
        media._run([*media._input(self.source), '-f', 'lavfi', '-i',
            'sine=frequency=440:duration=3', '-map', '0:v:0', '-map', '1:a:0',
            '-c:v', 'copy', '-c:a', 'aac', '-y', str(source)])
        with patch.object(editor, '_run', wraps=media._run) as commands:
            report = editor.replace_segment(source, self.alternate, .5, 1.5, out)
        bounded = [call.args[0] for call in commands.call_args_list if '-fs' in call.args[0]]
        self.assertEqual(len(bounded), 2)
        self.assertTrue(all(args[args.index('-fs') + 1] == str(editor.MAX_GENERATED_BYTES) for args in bounded))
        before, after = media._frame_hashes(source), media._frame_hashes(out)
        self.assertEqual(before[:12], after[:12])
        self.assertEqual(before[36:], after[36:])
        self.assertNotEqual(before[12:36], after[12:36])
        self.assertEqual(report['unchanged_frames_verified'], 48)
        self.assertEqual(report['timing']['video_duration_seconds'], 3)
        self.assertTrue(media._verify_timing(out, 72)['verified'])
        self.assertEqual(report['editor_version'], 'generated-media-v2')
        self.assertTrue(report['metadata']['has_audio'])
        def audio_digest(path):
            return media._run([*media._input(path), '-map', '0:a:0', '-vn',
                '-c:a', 'copy', '-f', 'hash', '-hash', 'sha256', '-']).stdout
        self.assertEqual(audio_digest(source), audio_digest(out))

    def test_truncated_master_never_published(self):
        out = self.root / 'truncated.mp4'
        with patch.object(editor, '_run'), \
                patch.object(editor, 'probe_generated', return_value={'duration': .5}), \
                patch.object(editor, '_frame_hashes') as hashes:
            with self.assertRaisesRegex(media.MediaError, 'master duration'):
                editor.replace_segment(self.source, self.alternate, 0, 1, out)
            hashes.assert_not_called()
        self.assertFalse(out.exists())

    def test_size_limited_master_never_published(self):
        out = self.root / 'oversized.mp4'
        def limited_encode(args):
            Path(args[-1]).write_bytes(b'\x00\x00\x00\x18ftypisom' + b'x' * (112 - 12))
        with patch.object(editor, 'MAX_GENERATED_BYTES', 128), \
                patch.object(editor, 'GENERATED_LIMIT_MARGIN', 16), \
                patch.object(editor, '_run', side_effect=limited_encode), \
                patch.object(editor, '_frame_hashes') as hashes:
            with self.assertRaisesRegex(media.MediaError, 'limit'):
                editor.replace_segment(self.source, self.alternate, 0, 1, out)
            hashes.assert_not_called()
        self.assertFalse(out.exists())
