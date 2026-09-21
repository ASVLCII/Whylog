import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = str(Path(__file__).with_name("whylog.py"))


class WhylogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.execute("git", "init", "-q")
        self.execute("git", "config", "user.name", "Whylog Test")
        self.execute("git", "config", "user.email", "whylog@example.test")
        (self.repo / "demo.txt").write_text("intentional line\n", encoding="utf-8")
        self.execute("git", "add", "demo.txt")
        self.execute("git", "commit", "-qm", "seed")

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, *command, ok=True):
        env = {**os.environ, "NO_COLOR": "1"}
        result = subprocess.run(command, cwd=self.repo, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ok and result.returncode:
            self.fail(result.stdout + result.stderr)
        return result

    def whylog(self, *args, ok=True):
        return self.execute(sys.executable, SCRIPT, *args, ok=ok)

    def test_log_links_commit_and_blob_and_configures_rewrite(self):
        result = self.whylog("log", "--type", "Decision", "--why", "keep it small",
                             "--prompt", "make it", "--model", "muse-spark-1.3", "--file", "demo.txt")
        self.assertIn("saved w", result.stdout)
        self.assertEqual("refs/notes/ai", self.execute("git", "config", "--get", "notes.rewriteRef").stdout.strip())
        for oid in (self.execute("git", "rev-parse", "HEAD").stdout.strip(),
                    self.execute("git", "rev-parse", "HEAD:demo.txt").stdout.strip()):
            self.assertIn("keep it small", self.execute("git", "notes", "--ref=ai", "show", oid).stdout)

    def test_why_uses_blame_and_blob_note(self):
        self.whylog("log", "--type", "Rejected", "--why", "too complex",
                    "--model", "muse-spark-1.3", "--file", "demo.txt")
        result = self.whylog("why", "demo.txt:1")
        self.assertIn("REJECTED  too complex", result.stdout)

    def test_list_deduplicates_commit_and_blob_notes(self):
        self.whylog("log", "--type", "Decision", "--why", "one record",
                    "--model", "muse-spark-1.3", "--file", "demo.txt")
        self.assertIn("1 entries", self.whylog("list").stdout)

    def test_watch_runs_once_for_matching_change(self):
        command = subprocess.list2cmdline([
            sys.executable, "-c", "from pathlib import Path;Path('watch.ok').write_text('ok')"
        ])
        self.whylog("log", "--type", "Watch", "--why", "verify text", "--model", "muse-spark-1.3",
                    "--watch-glob", "*.txt", "--watch-run", command, "--file", "demo.txt")
        (self.repo / "demo.txt").write_text("changed\n", encoding="utf-8")
        result = self.whylog("check")
        self.assertIn("1/1 triggered", result.stdout)
        self.assertEqual("ok", (self.repo / "watch.ok").read_text())

    def test_rejects_invalid_location(self):
        result = self.whylog("why", "demo.txt:nope", ok=False)
        self.assertEqual(1, result.returncode)
        self.assertIn("location must be path:line", result.stdout)


if __name__ == "__main__":
    unittest.main()
