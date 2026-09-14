"""Dotenv protection contract: secret files stay ignored and untracked.

The workspace already ignores `.env` and `.env.*` while allowing
`.env.example`. These tests prove that behavior plus proper file
termination, using only read-only Git queries. No secret file is ever
created in the worktree.
"""

import os
import shutil
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GITIGNORE_PATH = os.path.join(REPO_ROOT, ".gitignore")


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def require_git(testcase):
    if shutil.which("git") is None:
        testcase.skipTest("git is required for read-only ignore checks")


def is_ignored(path: str) -> bool:
    """True when Git ignores `path` (read-only `git check-ignore`)."""
    proc = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def tracked_files() -> list:
    """Read-only list of Git-tracked paths."""
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=True,
    )
    return proc.stdout.splitlines()


def is_tracked_dotenv_secret(path: str) -> bool:
    """True for a tracked dotenv secret (never `.env.example` itself)."""
    name = path.rsplit("/", 1)[-1]
    if name == ".env.example":
        return False
    return name == ".env" or name.startswith(".env.")


class GitignoreContentTests(unittest.TestCase):
    def test_dotenv_rules_present(self):
        text = read_text(GITIGNORE_PATH)
        lines = [line.strip() for line in text.splitlines()]
        self.assertIn(".env", lines)
        self.assertIn(".env.*", lines)
        self.assertIn("!.env.example", lines)

    def test_gitignore_ends_with_newline(self):
        with open(GITIGNORE_PATH, "rb") as handle:
            raw = handle.read()
        self.assertTrue(raw.endswith(b"\n"), ".gitignore must end with a newline")


class DotenvIgnoreBehaviorTests(unittest.TestCase):
    def test_env_and_env_local_are_ignored(self):
        require_git(self)
        self.assertTrue(is_ignored(".env"))
        self.assertTrue(is_ignored(".env.local"))

    def test_env_example_is_allowed(self):
        require_git(self)
        self.assertFalse(is_ignored(".env.example"))

    def test_no_tracked_dotenv_secret_exists(self):
        require_git(self)
        secrets = [path for path in tracked_files() if is_tracked_dotenv_secret(path)]
        self.assertEqual(secrets, [], f"tracked dotenv secrets: {secrets}")

    def test_secret_matcher_keeps_only_the_example(self):
        self.assertTrue(is_tracked_dotenv_secret(".env"))
        self.assertTrue(is_tracked_dotenv_secret(".env.local"))
        self.assertTrue(is_tracked_dotenv_secret("sub/dir/.env.production"))
        self.assertFalse(is_tracked_dotenv_secret(".env.example"))
        self.assertFalse(is_tracked_dotenv_secret("docs/.env.example"))
        # Ignored by `.env.*` but not un-ignored by `!.env.example`:
        # a tracked copy stays suspicious.
        self.assertTrue(is_tracked_dotenv_secret(".env.example.bak"))
        self.assertFalse(is_tracked_dotenv_secret("src/main.py"))


if __name__ == "__main__":
    unittest.main()
