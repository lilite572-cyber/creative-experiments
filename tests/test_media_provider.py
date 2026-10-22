import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import media, provider


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / "source.mp4"
        cls.replacement = cls.root / "replacement.mp4"
        media.make_demo(cls.source, "packaging", 3)
        media.make_demo(cls.replacement, "preparation", 2)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_probe_and_frames(self):
        metadata = media.probe(self.source)
        self.assertEqual(
            (metadata["width"], metadata["height"], metadata["fps"]), (320, 480, 24.0)
        )
        self.assertFalse(metadata["has_audio"])
        frames = media.extract_frames(self.source, self.root / "frames")
        self.assertEqual(len(frames), 8)
        self.assertEqual(frames[0]["time"], 0)
        self.assertTrue(all(frame["path"].is_file() for frame in frames))
        self.assertLess(frames[-1]["time"], metadata["duration"])

    def test_edit_and_independent_pixel_comparison(self):
        output = self.root / "edited.mp4"
        report = media.replace_segment(self.source, self.replacement, 0, 2, output)
        original = media._frame_hashes(self.source)
        edited = media._frame_hashes(output)
        self.assertEqual(len(original), len(edited))
        self.assertEqual(original[48:], edited[48:])
        self.assertNotEqual(original[0], edited[0])
        self.assertEqual(report["unchanged_frames_verified"], 24)
        self.assertEqual(report["replaced_frames"], 48)

    def test_eight_second_clip_keeps_exact_cfr_packet_timing(self):
        source, output = self.root / "eight.mp4", self.root / "eight-edited.mp4"
        media.make_demo(source, "packaging", 8)
        report = media.replace_segment(source, self.replacement, 0, 2, output)
        self.assertEqual(report["timing"]["video_duration_seconds"], 8)
        self.assertEqual(report["timing"]["frame_count"], 192)
        self.assertEqual(media.probe(output)["duration"], 8)
        self.assertEqual(media.probe(output)["fps"], 24)
        # Stream-copy packet report checks the final packet's exact duration too.
        self.assertEqual(media._verify_timing(output, 192)["video_duration_seconds"], 8)
        self.assertEqual(
            media._frame_hashes(source)[48:], media._frame_hashes(output)[48:]
        )

    def test_middle_edit_preserves_audio_and_tail(self):
        with_audio = self.root / "with-audio.mp4"
        media._run(
            [
                *media._input(self.source),
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=3",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-y",
                str(with_audio),
            ]
        )
        output = self.root / "middle.mp4"
        report = media.replace_segment(with_audio, self.replacement, 0.5, 1.5, output)
        original, edited = media._frame_hashes(with_audio), media._frame_hashes(output)
        self.assertEqual(original[:12], edited[:12])
        self.assertEqual(original[36:], edited[36:])
        self.assertTrue(media.probe(output)["has_audio"])
        self.assertEqual(report["timing"]["video_duration_seconds"], 3)
        self.assertTrue(media._verify_timing(output, 72)["verified"])

        def audio_hash(path):
            return media._run(
                [
                    *media._input(path),
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-f",
                    "hash",
                    "-hash",
                    "sha256",
                    "-",
                ]
            ).stdout

        self.assertEqual(audio_hash(with_audio), audio_hash(output))
        self.assertEqual(report["unchanged_frames_verified"], 48)
        wav = media.extract_audio(output, self.root / "audio.wav")
        self.assertTrue(wav.is_file())

    def test_invalid_and_unaligned_edits(self):
        for start, end in [(0, 0), (-1, 1), (0, 4), (0, 0.01), (float("nan"), 1)]:
            with self.assertRaises(media.MediaError):
                media.replace_segment(
                    self.source, self.replacement, start, end, self.root / "bad.mp4"
                )
        self.assertFalse((self.root / "bad.mp4").exists())

    def test_oversized_metadata_rejected_before_frame_decode(self):
        from subprocess import CompletedProcess

        metadata = b"Duration: 00:00:03.00\n  Stream #0:0: Video: h264, yuv420p, 4096x4096, 24 fps\n"
        with patch(
            "app.media._run", return_value=CompletedProcess([], 0, b"", metadata)
        ) as run:
            with self.assertRaisesRegex(
                media.MediaError, "Maximum supported image size"
            ):
                media.probe(self.source)
            self.assertEqual(run.call_count, 1)
            args = run.call_args.args[0]
            self.assertEqual(args[args.index("-frames:v") + 1], "0")
            self.assertEqual(args[args.index("-c:v") + 1], "copy")

    def test_invalid_file_and_reject_output_overwrite(self):
        bad = self.root / "not.mp4"
        bad.write_bytes(b"not a video file")
        with self.assertRaises(media.MediaError):
            media.probe(bad)
        with self.assertRaises(media.MediaError):
            media.replace_segment(self.source, self.replacement, 0, 1, self.source)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "duration": 8,
            "fps": 24,
            "width": 320,
            "height": 480,
            "has_audio": False,
        }
        self.frames = [{"path": Path("/unused"), "index": 0, "time": 0.0}]
        self.payload = {
            "hook_category": "packaging",
            "observations": [
                {
                    "frame_index": 0,
                    "kind": "hook",
                    "text": "A coffee package is visible.",
                }
            ],
        }
        self.response = {
            "status": "completed",
            "model": provider.MODEL,
            "id": "test-response",
            "usage": {"input_tokens": 1000, "output_tokens": 100},
            "output": [
                {"content": [{"type": "output_text", "text": json.dumps(self.payload)}]}
            ],
        }

    def test_disabled_without_network(self):
        with patch("app.provider._post_json") as post:
            with self.assertRaises(provider.ProviderError):
                provider.analyze(Path("/unused"), self.metadata, self.frames)
            post.assert_not_called()

    def test_structured_result_cost_and_evidence(self):
        result, audit = provider.validate_response(
            self.response, self.metadata, self.frames
        )
        self.assertEqual(result["segments"][0]["start"], 0)
        self.assertEqual(result["segments"][0]["end"], 1 / 24)
        self.assertEqual(result["speech_status"], "not_transcribed")
        self.assertAlmostEqual(audit["cost_usd"], 0.00056)

    def test_unknown_evidence_and_bad_schema(self):
        for invalid in [
            dict(
                self.payload,
                observations=[{"frame_index": 999, "kind": "hook", "text": "invented"}],
            ),
            dict(
                self.payload,
                observations=[
                    {"frame_index": 0, "kind": "speech", "text": "inferred speech"}
                ],
            ),
            dict(self.payload, fabricated_metric=0.9),
        ]:
            response = copy.deepcopy(self.response)
            response["output"][0]["content"][0]["text"] = json.dumps(invalid)
            with self.assertRaises(provider.ProviderError):
                provider.validate_response(response, self.metadata, self.frames)

    def test_malformed_envelopes_are_safe_provider_errors(self):
        for output in [None, "wrong", [None], [{"content": 3}], [{"content": [None]}]]:
            with self.assertRaises(provider.ProviderError):
                provider.validate_response(
                    dict(self.response, output=output), self.metadata, self.frames
                )

    def test_incomplete_wrong_model_missing_usage(self):
        for field, value in [("status", "incomplete"), ("model", "other")]:
            with self.assertRaises(provider.ProviderError):
                provider.validate_response(
                    dict(self.response, **{field: value}), self.metadata, self.frames
                )
        response = dict(self.response, usage={})
        self.assertIsNone(
            provider.validate_response(response, self.metadata, self.frames)[1][
                "cost_usd"
            ]
        )

    def test_fake_transport_only(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "frame.jpg"
            from PIL import Image

            Image.new("RGB", (32, 32)).save(image)
            frames = [dict(self.frames[0], path=image)]
            seen = []

            def transport(request):
                seen.append(request)
                return self.response

            with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-fixture-key"}), patch(
                "app.provider._post_json"
            ) as live:
                analysis, audit = provider.analyze(
                    Path("/unused"),
                    self.metadata,
                    frames,
                    authorized=True,
                    transport=transport,
                )
                live.assert_not_called()
            self.assertEqual(len(seen), 1)
            self.assertTrue(seen[0]["text"]["format"]["strict"])
            self.assertEqual(audit["attempts"], 1)
            self.assertNotIn("fake-fixture-key", json.dumps((analysis, audit)))

    def test_proposal_preserves_evidence_and_rejects_fabrication(self):
        candidate = {
            "id": "candidate-a",
            "stats": {"n": 4, "delta_pp": 3.1},
            "sources": [{"video_id": "video-a", "start": 0, "end": 2}],
            "kind": "exploratory",
        }
        item = {
            "candidate_id": "candidate-a",
            "hypothesis": "Preparation may retain viewers better.",
            "change": "Replace the opening with preparation.",
            "preserve": ["Offer and remaining footage"],
            "explanation": "Treat this as an exploratory test.",
        }

        def transport(request):
            self.assertTrue(request["text"]["format"]["strict"])
            response = copy.deepcopy(self.response)
            response["output"][0]["content"][0]["text"] = json.dumps(
                {"recommendations": [item]}
            )
            return response

        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}):
            with self.assertRaises(provider.ProviderError):
                provider.propose([candidate], transport=transport)
            result, audit = provider.propose(
                [candidate], authorized=True, transport=transport
            )
            self.assertEqual(result[0]["sources"], candidate["sources"])
            self.assertEqual(result[0]["stats"], candidate["stats"])
            item["candidate_id"] = "unknown"
            with self.assertRaises(provider.ProviderError):
                provider.propose([candidate], authorized=True, transport=transport)
            item["candidate_id"] = "candidate-a"
            item["explanation"] = "Retention will increase by 99%."
            with self.assertRaises(provider.ProviderError):
                provider.propose([candidate], authorized=True, transport=transport)

    def test_timeout_not_retried(self):
        import httpx

        with patch("app.provider.httpx.Client") as client:
            client.return_value.__enter__.return_value.stream.side_effect = (
                httpx.ReadTimeout("private host detail")
            )
            with self.assertRaisesRegex(
                provider.ProviderError, "billing outcome may be unknown"
            ):
                provider._post_json({}, "fake")
            self.assertEqual(
                client.return_value.__enter__.return_value.stream.call_count, 1
            )


if __name__ == "__main__":
    unittest.main()
