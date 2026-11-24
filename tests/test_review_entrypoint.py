from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ARTIFACT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("authrefine_review", ARTIFACT / "review.py")
assert SPEC is not None and SPEC.loader is not None
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)


class ReviewEntrypointTests(unittest.TestCase):
    def test_success_records_file_backed_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            row = REVIEW.run_step(name="success", command=[sys.executable, "-c", "print('review-ok')"], cwd=ARTIFACT, output=output, timeout=10)
            self.assertTrue(row["ok"])
            self.assertFalse(row["timed_out"])
            self.assertEqual(row["returncode"], 0)
            self.assertEqual((output / row["stdout"]).read_text().strip(), "review-ok")

    def test_failure_is_not_reported_as_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            row = REVIEW.run_step(name="failure", command=[sys.executable, "-c", "raise SystemExit(7)"], cwd=ARTIFACT, output=output, timeout=10)
            self.assertFalse(row["ok"])
            self.assertFalse(row["timed_out"])
            self.assertEqual(row["returncode"], 7)

    def test_output_directory_contract(self) -> None:
        default = REVIEW.prepare_output(None)
        self.assertTrue(default.is_dir())
        with tempfile.TemporaryDirectory() as directory:
            requested = Path(directory) / "fresh"
            created = REVIEW.prepare_output(requested)
            self.assertEqual(created, requested.resolve())
            self.assertTrue(created.is_dir())
            with self.assertRaises(FileExistsError):
                REVIEW.prepare_output(requested)

    def test_timeout_kills_descendants_and_returns_receipt(self) -> None:
        script = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); time.sleep(60)"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            row = REVIEW.run_step(name="timeout", command=[sys.executable, "-c", script], cwd=ARTIFACT, output=output, timeout=1)
            self.assertFalse(row["ok"])
            self.assertTrue(row["timed_out"])
            self.assertEqual(row["returncode"], 124)
            self.assertLess(row["seconds"], 15)


if __name__ == "__main__":
    unittest.main()
