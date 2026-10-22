"""Safety boundaries of the two-project launch command; no network or real keys."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_authorized_pilots as runner


class CombinedPilotTests(unittest.TestCase):
    def test_briefguard_only_excludes_creative_from_check_and_execution(self):
        with patch.object(runner, "preflight", return_value={"ready": True}) as check, \
             patch.object(runner, "load_private_key", return_value="fake-test-key"), \
             patch.object(runner, "provider_check", return_value={"available": True}), \
             patch.object(runner, "execute", return_value=0) as execute:
            self.assertEqual(runner.main(["--project", "briefguard", "--execute"]), 0)
            selected = check.call_args.args[0]
            self.assertEqual([job["name"] for job in selected], ["BriefGuard"])
            self.assertEqual(execute.call_args.args[0], selected)
            self.assertIn("--approve-openai-gpt41mini-usd050", selected[0]["execute"])

    def test_briefguard_only_does_not_execute_when_provider_is_unavailable(self):
        with patch.object(runner, "preflight", return_value={"ready": True}), \
             patch.object(runner, "load_private_key", return_value="fake-test-key"), \
             patch.object(runner, "provider_check", return_value={"available": False}), \
             patch.object(runner, "execute") as execute:
            self.assertEqual(runner.main(["--project", "briefguard", "--execute"]), 2)
            execute.assert_not_called()

    def test_execute_never_reads_key_or_contacts_provider_when_review_is_missing(self):
        with patch.object(runner, "preflight", return_value={"ready": False}), \
                patch.object(runner, "load_private_key") as key, \
                patch.object(runner, "provider_check") as provider, \
                patch.object(runner, "execute") as execute:
            self.assertEqual(runner.main(["--execute"]), 2)
            key.assert_not_called()
            provider.assert_not_called()
            execute.assert_not_called()

    def test_stops_before_second_project_on_first_execution_failure(self):
        jobs = [{"name": name, "cwd": Path.cwd(), "execute": ["fake-command"]}
                for name in ["first", "second"]]
        with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 2, "saved failure", "")) as invoke:
            self.assertEqual(runner.execute(jobs, "test-only-not-a-credential"), 2)
            self.assertEqual(invoke.call_count, 1)
            self.assertNotIn("test-only-not-a-credential", invoke.call_args.args[0])

    def test_key_symlink_and_world_readable_file_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "key"
            path.write_text("sk-" + "a" * 30)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                runner.load_private_key(path)
            path.chmod(0o600)
            link = path.with_name("link")
            link.symlink_to(path)
            with self.assertRaises(OSError):
                runner.load_private_key(link)
            self.assertEqual(runner.load_private_key(path), "sk-" + "a" * 30)

    def test_metadata_check_sends_only_get_and_never_prints_response_body(self):
        with patch.object(runner.httpx, "Client") as client:
            response = client.return_value.__enter__.return_value.get.return_value
            response.status_code = 401
            response.json.side_effect = AssertionError("Do not decode provider error bodies")
            result = runner.provider_check("test-only-not-a-credential")
            self.assertFalse(result["available"])
            self.assertEqual(result["inference_requests"], 0)
            client.return_value.__enter__.return_value.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
