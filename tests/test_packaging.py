import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_FILES = {"agents.md", "claude.md", "gemini.md", ".cursorrules"}


class PackagingTests(unittest.TestCase):
    def test_no_agent_workflow_files_ship_in_the_plugin(self):
        tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True,
                                 capture_output=True).stdout.decode().split("\0")
        shipped = [path for path in tracked if path and (
            Path(path).name.lower() in WORKFLOW_FILES or ".cursor" in Path(path).parts)]
        self.assertEqual(shipped, [])


if __name__ == "__main__":
    unittest.main()
