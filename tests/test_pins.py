"""Source Checksum pin contracts (threat-matrix RED tests).

Covers the design threat matrix for the pin boundary:

* Documentation-like/non-AppImage paths are rejected; a matching SHA-256
  digest is accepted and changed bytes are rejected.
* `git -C` outside GITHUB_WORKSPACE, empty index/extra staged files,
  `commit -a`, hostile refspecs, missing tracking, non-origin pushes,
  composed feed arguments, missing `--head`, and missing secrets are
  rejected.
* A same-version repin preserves the metainfo release date (no date
  churn); only a genuinely new upstream version stamps the runner UTC date.
* Automated approval targets only the exact pin PR after OPEN/head/base/
  author identity checks, running as github.token while the App token keeps
  branch push, PR creation, and auto-merge. Identity validation precedes
  every mutation in both token contexts, and PR creation pins --base main.

Pure helpers are unit-tested with hostile fixtures. Repo-content tests
assert the real `data/pins.yml` and `.github/workflows/pin.yml` satisfy
the same contracts; they fail (RED) until task 2.1 creates those files.
"""

import hashlib
import hmac
import os
import re
import shlex
import unittest
from urllib.parse import urlsplit

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PINS_PATH = os.path.join(REPO_ROOT, "data", "pins.yml")
PIN_WORKFLOW_PATH = os.path.join(REPO_ROOT, ".github", "workflows", "pin.yml")

FEED_X64 = "https://api2.cursor.sh/updates/api/download/stable/linux-x64/sand"
FEED_ARM64 = "https://api2.cursor.sh/updates/api/download/stable/linux-arm64/sand"
ALLOWED_FEEDS = {FEED_X64, FEED_ARM64}
ARTIFACT_HOST = "downloads.cursor.com"
ALLOWED_PIN_PATHS = {"data/pins.yml", "io.github.viniciosrab.GrokBot.yml", "data/io.github.viniciosrab.GrokBot.metainfo.xml"}
REQUIRED_PIN_SECRETS = ("APP_ID", "APP_PRIVATE_KEY")
ALLOWED_PUSH_REMOTE = "origin"
EXPECTED_PIN_AUTHOR = "grok-bot-pin[bot]"
EXPECTED_PIN_BASE = "main"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
DOCS_BASENAME_RES = (
    re.compile(r"\.(md|mdx|markdown|txt|rst|sh)$", re.IGNORECASE),
    re.compile(r"^(requirements\.txt|cmakelists\.txt|makefile|readme)", re.IGNORECASE),
)


# ---------------------------------------------------------------------------
# Minimal mapping-only YAML reader (stdlib only).
# ---------------------------------------------------------------------------

def parse_simple_yaml_mapping(text: str) -> dict:
    """Parse flat/nested `key: value` mappings (2-space indent, no lists).

    Raises ValueError on anything outside that subset so pins.yml stays
    machine-checkable without a YAML dependency. Fail-closed by design.
    """
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split(" # ", 1)[0].rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if stripped.startswith("- "):
            raise ValueError(f"line {lineno}: lists are not supported in pins.yml")
        if ":" not in stripped:
            raise ValueError(f"line {lineno}: expected `key: value`")
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if not key or " " in key:
            raise ValueError(f"line {lineno}: invalid key {key!r}")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if key in parent:
            raise ValueError(f"line {lineno}: duplicate key {key!r}")
        if value == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            parent[key] = value
    return root


def load_pins() -> dict:
    with open(PINS_PATH, "r", encoding="utf-8") as handle:
        return parse_simple_yaml_mapping(handle.read())


# ---------------------------------------------------------------------------
# Artifact digest helpers.
# ---------------------------------------------------------------------------

def is_hex_digest(value: object) -> bool:
    return isinstance(value, str) and bool(HEX64_RE.match(value))


def verify_bytes_against_digest(data: bytes, digest: str) -> bool:
    """Accept only bytes whose SHA-256 matches the pinned digest."""
    if not is_hex_digest(digest):
        return False
    actual = hashlib.sha256(data).hexdigest()
    return hmac.compare_digest(actual, digest)


def is_appimage_artifact_url(url: object) -> bool:
    """Accept only https AppImage artifact URLs; reject docs-like paths."""
    if not isinstance(url, str) or not url or " " in url:
        return False
    if not url.startswith("https://"):
        return False
    if "?" in url or "#" in url:
        return False
    path = url
    if not path.endswith(".AppImage"):
        return False
    basename = path.rsplit("/", 1)[-1]
    if not basename or basename == ".AppImage":
        return False
    for pattern in DOCS_BASENAME_RES:
        if pattern.search(basename):
            return False
    return True


def artifact_host_is_pinned(url: object) -> bool:
    """Accept only artifact URLs whose hostname exactly matches the pin."""
    try:
        return urlsplit(url).hostname == ARTIFACT_HOST
    except Exception:
        return False


def validate_pins_schema(pins: dict) -> list:
    """Return a list of schema violations (empty means valid)."""
    errors = []
    if not isinstance(pins, dict):
        return ["pins.yml must be a mapping"]
    if not VERSION_RE.match(str(pins.get("version", ""))):
        errors.append("version must look like 0.47.0")
    if not COMMIT_SHA_RE.match(str(pins.get("commitSha", ""))):
        errors.append("commitSha must be a 40-char hex digest")
    arches = pins.get("architectures")
    if not isinstance(arches, dict) or set(arches) != {"x86_64", "aarch64"}:
        errors.append("architectures must define exactly x86_64 and aarch64")
        return errors
    expected_feeds = {"x86_64": FEED_X64, "aarch64": FEED_ARM64}
    for arch, entry in arches.items():
        if not isinstance(entry, dict):
            errors.append(f"{arch}: entry must be a mapping")
            continue
        if entry.get("feed") != expected_feeds[arch]:
            errors.append(f"{arch}: feed must be the sand feed, nothing else")
        url = entry.get("url", "")
        if not is_appimage_artifact_url(url):
            errors.append(f"{arch}: url must be an AppImage artifact URL")
        elif not artifact_host_is_pinned(url):
            errors.append(f"{arch}: url must stay on {ARTIFACT_HOST}")
        if not is_hex_digest(entry.get("sha256")):
            errors.append(f"{arch}: sha256 must be a 64-char hex Source Checksum")
    return errors


# ---------------------------------------------------------------------------
# Git safety helpers (argv-list based, no shell).
# ---------------------------------------------------------------------------

_ENV_PREFIX_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


def strip_env_prefix(argv: list) -> list:
    cleaned = list(argv)
    while cleaned and _ENV_PREFIX_RE.match(cleaned[0]):
        cleaned.pop(0)
    return cleaned


def has_unsafe_c_flag(argv: list, workspace: str) -> bool:
    """Reject every `git -C <path>` that does not stay in the workspace."""
    tokens = strip_env_prefix(argv)
    for index, token in enumerate(tokens):
        if token == "-C":
            if index + 1 >= len(tokens) or tokens[index + 1] != workspace:
                return True
        elif token.startswith("-C") and token != "-C":
            if token[2:] != workspace:
                return True
    return False


def pin_commit_is_path_only(argv: list, allowed: set = ALLOWED_PIN_PATHS) -> bool:
    """Accept only `git commit -- <allowed paths>` (never bare, never -a)."""
    tokens = strip_env_prefix(argv)
    if len(tokens) < 2 or tokens[0] != "git" or tokens[1] != "commit":
        return False
    if "-a" in tokens or "--all" in tokens:
        return False
    if "--" not in tokens:
        return False
    paths = tokens[tokens.index("--") + 1:]
    if not paths:
        return False
    return set(paths) <= set(allowed)


def git_add_is_path_only(argv: list, allowed: set = ALLOWED_PIN_PATHS) -> bool:
    tokens = strip_env_prefix(argv)
    if len(tokens) < 2 or tokens[0] != "git" or tokens[1] != "add":
        return False
    if "-A" in tokens or "--all" in tokens or "." in tokens:
        return False
    if "--" not in tokens:
        return False
    paths = tokens[tokens.index("--") + 1:]
    return bool(paths) and set(paths) <= set(allowed)


def push_is_origin_branch(argv: list) -> bool:
    """Accept only `git push origin pin/<name>` (explicit, no refspec)."""
    tokens = strip_env_prefix(argv)
    if len(tokens) != 4:
        return False
    if tokens[0] != "git" or tokens[1] != "push":
        return False
    if tokens[2] != ALLOWED_PUSH_REMOTE:
        return False
    branch = tokens[3]
    if not branch.startswith("pin/"):
        return False
    if ":" in branch or branch.startswith("+") or branch.startswith("-"):
        return False
    return True


def gh_pr_create_has_head(argv: list) -> bool:
    """Accept only `gh pr create --head <branch> ...` (with --head)."""
    tokens = strip_env_prefix(argv)
    if tokens and tokens[0] == "gh":
        tokens = tokens[1:]
    if "pr" not in tokens or "create" not in tokens:
        return False
    if tokens.index("create") < tokens.index("pr"):
        return False
    if "--head" not in tokens:
        return False
    head_index = tokens.index("--head")
    if head_index + 1 >= len(tokens):
        return False
    head = tokens[head_index + 1]
    return bool(head) and not head.startswith("-")


def gh_pr_merge_is_exact_auto_squash(argv: list) -> bool:
    """Accept only `gh pr merge --auto --squash \"${PR_NUMBER}\"` (exact PR).

    The merge must target the captured PR number variable, never a branch
    name, and must request auto-merge (never an immediate merge that would
    bypass the required PR checks gating the merge).
    """
    tokens = strip_env_prefix(argv)
    if tokens and tokens[0] == "gh":
        tokens = tokens[1:]
    if "pr" not in tokens or "merge" not in tokens:
        return False
    if tokens.index("merge") < tokens.index("pr"):
        return False
    if "--auto" not in tokens:
        return False
    if "--squash" not in tokens:
        return False
    merge_index = tokens.index("merge")
    tail = tokens[merge_index + 1:]
    targets = [token for token in tail if not token.startswith("-")]
    return targets == ["${PR_NUMBER}"]


def metainfo_release_entry(pinned_version, existing_version, existing_date, today):
    """Return the metainfo `<release .../>` entry for a pin run.

    A same-version repin preserves the existing release date (no date
    churn); only a genuinely new upstream version stamps the current UTC
    date. Returns None on any invalid input so callers fail closed.
    """
    if not VERSION_RE.match(str(pinned_version or "")):
        return None
    if not VERSION_RE.match(str(existing_version or "")):
        return None
    if not DATE_RE.match(str(existing_date or "")):
        return None
    if not DATE_RE.match(str(today or "")):
        return None
    if existing_version == pinned_version:
        return '<release version="%s" date="%s"/>' % (pinned_version, existing_date)
    return '<release version="%s" date="%s"/>' % (pinned_version, today)


def pin_pr_identity_is_valid(number, state, head, base, author, expected_head):
    """Accept only the exact pin PR after full identity checks.

    The number must be a positive all-digit PR number, the state must be
    OPEN, the head ref must equal the expected pin branch, the base ref
    must be main, and the author must be the pin App bot. Anything else
    fails closed so approval can never land on a foreign PR.
    """
    if not isinstance(number, str) or not number.isdigit() or int(number) <= 0:
        return False
    if state != "OPEN":
        return False
    if not expected_head or head != expected_head:
        return False
    if base != EXPECTED_PIN_BASE:
        return False
    return author == EXPECTED_PIN_AUTHOR


def porcelain_shows_only_allowed(output: str, allowed: set = ALLOWED_PIN_PATHS) -> bool:
    """Check `git status --porcelain` lists only allowed paths."""
    seen = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        seen.add(path)
    return seen <= set(allowed)


# ---------------------------------------------------------------------------
# Workflow shell-safety helpers.
# ---------------------------------------------------------------------------

_RUN_BLOCK_RE = re.compile(r"^(\s*)run:\s*(\||>)\s*$")
_UNSAFE_RUN_RES = (
    re.compile(r"\$\{\{"),
    re.compile(r"`"),
    re.compile(r"(?<![A-Za-z0-9_])eval\s"),
    re.compile(r"steps\.", re.IGNORECASE),
    re.compile(r"needs\.", re.IGNORECASE),
)


def run_blocks_of(text: str) -> list:
    """Extract `run: |` shell blocks from a workflow file."""
    blocks = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = _RUN_BLOCK_RE.match(lines[index])
        if not match:
            index += 1
            continue
        base_indent = len(match.group(1))
        index += 1
        collected = []
        while index < len(lines):
            line = lines[index]
            if line.strip() == "":
                collected.append(line)
                index += 1
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent <= base_indent:
                break
            collected.append(line)
            index += 1
        blocks.append("\n".join(collected))
    return blocks


def run_block_is_shell_safe(block: str) -> bool:
    """Reject composed feed arguments in shell: no ${{}}, backticks, eval,
    or steps./needs. references. Feed values travel via env/files only."""
    return not any(pattern.search(block) for pattern in _UNSAFE_RUN_RES)


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def workflow_step_containing(text: str, marker: str) -> str:
    """Return the `- name:` step block containing marker, or "" when absent."""
    steps = re.split(r"\n(?=      - name: )", text)
    for step in steps:
        if marker in step:
            return step
    return ""


# ---------------------------------------------------------------------------
# Unit tests: hostile fixtures for the pure helpers.
# ---------------------------------------------------------------------------

class YamlSubsetTests(unittest.TestCase):
    def test_parses_nested_pins_shape(self):
        pins = parse_simple_yaml_mapping(
            "version: 0.47.0\ncommitSha: abc123\narchitectures:\n"
            "  x86_64:\n    url: https://example/x.AppImage\n    sha256: dead\n"
        )
        self.assertEqual(pins["version"], "0.47.0")
        self.assertEqual(pins["architectures"]["x86_64"]["sha256"], "dead")

    def test_rejects_lists_and_duplicates(self):
        with self.assertRaises(ValueError):
            parse_simple_yaml_mapping("a:\n  - one\n")
        with self.assertRaises(ValueError):
            parse_simple_yaml_mapping("a: 1\na: 2\n")


class DigestContractTests(unittest.TestCase):
    def test_matching_digest_accepted(self):
        data = b"grok-bot-pinned-bytes"
        digest = hashlib.sha256(data).hexdigest()
        self.assertTrue(verify_bytes_against_digest(data, digest))

    def test_changed_bytes_rejected(self):
        data = b"grok-bot-pinned-bytes"
        digest = hashlib.sha256(data).hexdigest()
        self.assertFalse(verify_bytes_against_digest(data + b"x", digest))
        self.assertFalse(verify_bytes_against_digest(b"", digest))

    def test_malformed_digests_rejected(self):
        self.assertFalse(verify_bytes_against_digest(b"x", "not-a-digest"))
        self.assertFalse(verify_bytes_against_digest(b"x", "c082fda9"))
        self.assertFalse(verify_bytes_against_digest(b"x", "Z" * 64))
        self.assertFalse(verify_bytes_against_digest(b"x", None))


class ArtifactUrlContractTests(unittest.TestCase):
    GOOD = (
        "https://downloads.cursor.com/grokbot/stable/abc/linux/x64/Grok_Bot_0.47.0.AppImage"
    )

    def test_appimage_url_accepted(self):
        self.assertTrue(is_appimage_artifact_url(self.GOOD))

    def test_documentation_like_paths_rejected(self):
        for bad in (
            "https://example.com/requirements.txt",
            "https://example.com/CMakeLists.txt",
            "https://example.com/README.md",
            "https://example.com/guide.mdx",
            "https://example.com/README.sh",
            "https://example.com/docs/notes.txt",
            "https://example.com/grok-bot_0.47.0_amd64.deb",
            "https://example.com/grok-bot-0.47.0-1.x86_64.rpm",
            "http://downloads.cursor.com/x.AppImage",
            "https://downloads.cursor.com/x.AppImage?sig=abc",
            "",
            None,
        ):
            self.assertFalse(is_appimage_artifact_url(bad), bad)

    def test_artifact_host_requires_exact_hostname(self):
        self.assertTrue(artifact_host_is_pinned(self.GOOD))
        self.assertFalse(
            artifact_host_is_pinned("https://downloads.cursor.com.evil/x.AppImage")
        )
        self.assertFalse(artifact_host_is_pinned(None))
        self.assertFalse(
            is_appimage_artifact_url("http://downloads.cursor.com/x.AppImage")
        )
        self.assertFalse(
            is_appimage_artifact_url(
                "https://downloads.cursor.com/x.AppImage?sig=abc"
            )
        )


class GitSafetyHelperTests(unittest.TestCase):
    WORKSPACE = "/github/workspace"

    def test_c_flag_outside_workspace_rejected(self):
        self.assertTrue(has_unsafe_c_flag(["git", "-C", "..", "status"], self.WORKSPACE))
        self.assertTrue(
            has_unsafe_c_flag(["git", "-C", "/tmp/evil", "status"], self.WORKSPACE)
        )
        self.assertTrue(has_unsafe_c_flag(["git", "-C/tmp/evil", "status"], self.WORKSPACE))
        self.assertFalse(has_unsafe_c_flag(["git", "status"], self.WORKSPACE))
        self.assertFalse(
            has_unsafe_c_flag(["git", "-C", self.WORKSPACE, "status"], self.WORKSPACE)
        )

    def test_commit_requires_explicit_pin_path(self):
        good = ["git", "commit", "-m", "chore(pin): sand 0.47.0", "--", "data/pins.yml"]
        self.assertTrue(pin_commit_is_path_only(good))
        triple = [
            "git", "commit", "-m", "chore(pin): sand 0.47.0", "--",
            "data/pins.yml",
            "io.github.viniciosrab.GrokBot.yml",
            "data/io.github.viniciosrab.GrokBot.metainfo.xml",
        ]
        self.assertTrue(pin_commit_is_path_only(triple))
        self.assertFalse(pin_commit_is_path_only(["git", "commit", "-a", "-m", "x"]))
        self.assertFalse(pin_commit_is_path_only(["git", "commit", "--all", "-m", "x"]))
        self.assertFalse(pin_commit_is_path_only(["git", "commit", "-m", "x"]))
        self.assertFalse(
            pin_commit_is_path_only(
                ["git", "commit", "-m", "x", "--", "data/pins.yml", "extra.txt"]
            )
        )
        self.assertFalse(
            pin_commit_is_path_only(
                [
                    "git", "commit", "-m", "x", "--",
                    "data/pins.yml",
                    "io.github.viniciosrab.GrokBot.yml",
                    "data/io.github.viniciosrab.GrokBot.metainfo.xml",
                    "extra.txt",
                ]
            )
        )

    def test_add_requires_explicit_pin_path(self):
        self.assertTrue(git_add_is_path_only(["git", "add", "--", "data/pins.yml"]))
        self.assertTrue(
            git_add_is_path_only(
                [
                    "git", "add", "--",
                    "data/pins.yml",
                    "io.github.viniciosrab.GrokBot.yml",
                    "data/io.github.viniciosrab.GrokBot.metainfo.xml",
                ]
            )
        )
        self.assertFalse(git_add_is_path_only(["git", "add", "-A"]))
        self.assertFalse(git_add_is_path_only(["git", "add", "."]))
        self.assertFalse(
            git_add_is_path_only(
                [
                    "git", "add", "--",
                    "data/pins.yml",
                    "io.github.viniciosrab.GrokBot.yml",
                    "data/io.github.viniciosrab.GrokBot.metainfo.xml",
                    "extra.txt",
                ]
            )
        )

    def test_push_must_be_origin_pin_branch(self):
        self.assertTrue(push_is_origin_branch(["git", "push", "origin", "pin/sand-0.47.0"]))
        self.assertFalse(push_is_origin_branch(["git", "push"]))  # missing tracking
        self.assertFalse(
            push_is_origin_branch(["git", "push", "evil", "pin/sand-0.47.0"])
        )
        self.assertFalse(
            push_is_origin_branch(
                ["git", "push", "origin", "HEAD:refs/heads/pin/sand-0.47.0"]
            )
        )
        self.assertFalse(
            push_is_origin_branch(["git", "push", "--force", "origin", "pin/x"])
        )
        self.assertFalse(push_is_origin_branch(["git", "push", "origin", "main"]))

    def test_pr_create_requires_head(self):
        self.assertTrue(
            gh_pr_create_has_head(
                ["gh", "pr", "create", "--head", "pin/sand-0.47.0", "--title", "t"]
            )
        )
        self.assertTrue(
            gh_pr_create_has_head(
                ["GH_TOKEN=x", "gh", "pr", "create", "--head", "pin/y", "--title", "t"]
            )
        )
        self.assertFalse(gh_pr_create_has_head(["gh", "pr", "create", "--title", "t"]))
        self.assertFalse(gh_pr_create_has_head(["gh", "pr", "create", "--head"]))

    def test_pr_merge_requires_exact_auto_squash_target(self):
        self.assertTrue(
            gh_pr_merge_is_exact_auto_squash(
                ["gh", "pr", "merge", "--auto", "--squash", "${PR_NUMBER}"]
            )
        )
        self.assertTrue(
            gh_pr_merge_is_exact_auto_squash(
                ["GH_TOKEN=x", "gh", "pr", "merge", "--auto", "--squash", "${PR_NUMBER}"]
            )
        )
        # Immediate merge without --auto would bypass required PR checks before merge.
        self.assertFalse(
            gh_pr_merge_is_exact_auto_squash(
                ["gh", "pr", "merge", "--squash", "${PR_NUMBER}"]
            )
        )
        # Ambiguous branch targeting is rejected; only the exact PR number counts.
        self.assertFalse(
            gh_pr_merge_is_exact_auto_squash(
                ["gh", "pr", "merge", "--auto", "--squash", "${PIN_BRANCH}"]
            )
        )
        self.assertFalse(
            gh_pr_merge_is_exact_auto_squash(
                ["gh", "pr", "merge", "--auto", "--squash", "pin/sand-0.47.0"]
            )
        )
        # A non-squash merge method is rejected for pin PRs.
        self.assertFalse(
            gh_pr_merge_is_exact_auto_squash(
                ["gh", "pr", "merge", "--auto", "--merge", "${PR_NUMBER}"]
            )
        )
        self.assertFalse(
            gh_pr_merge_is_exact_auto_squash(["gh", "pr", "merge", "--auto", "--squash"])
        )

    def test_pin_pr_identity_checks_reject_foreign_prs(self):
        good = ("42", "OPEN", "pin/sand-0.47.0", "main", "grok-bot-pin[bot]")
        self.assertTrue(pin_pr_identity_is_valid(*good, "pin/sand-0.47.0"))
        # Non-positive or non-numeric numbers never identify a PR.
        for bad_number in ("", "0", "-3", "4.2", "12a", None, 42):
            bad = (bad_number, "OPEN", "pin/sand-0.47.0", "main", "grok-bot-pin[bot]")
            self.assertFalse(pin_pr_identity_is_valid(*bad, "pin/sand-0.47.0"), bad_number)
        # Only OPEN PRs may be approved.
        for state in ("CLOSED", "MERGED", "", None):
            bad = ("42", state, "pin/sand-0.47.0", "main", "grok-bot-pin[bot]")
            self.assertFalse(pin_pr_identity_is_valid(*bad, "pin/sand-0.47.0"), state)
        # Head must equal the expected pin branch, base must be main.
        bad = ("42", "OPEN", "pin/sand-0.48.0", "main", "grok-bot-pin[bot]")
        self.assertFalse(pin_pr_identity_is_valid(*bad, "pin/sand-0.47.0"))
        bad = ("42", "OPEN", "main", "main", "grok-bot-pin[bot]")
        self.assertFalse(pin_pr_identity_is_valid(*bad, "pin/sand-0.47.0"))
        bad = ("42", "OPEN", "pin/sand-0.47.0", "pin/sand-0.47.0", "grok-bot-pin[bot]")
        self.assertFalse(pin_pr_identity_is_valid(*bad, "pin/sand-0.47.0"))
        self.assertFalse(
            pin_pr_identity_is_valid("42", "OPEN", "pin/sand-0.47.0", "main", "grok-bot-pin[bot]", "")
        )
        # Only the pin App bot may author an approvable pin PR.
        for author in ("octocat", "github-actions[bot]", "dependabot[bot]", "", None):
            bad = ("42", "OPEN", "pin/sand-0.47.0", "main", author)
            self.assertFalse(pin_pr_identity_is_valid(*bad, "pin/sand-0.47.0"), author)

    def test_metainfo_release_date_preserved_on_same_version(self):
        self.assertEqual(
            metainfo_release_entry("0.47.0", "0.47.0", "2026-09-01", "2026-09-13"),
            '<release version="0.47.0" date="2026-09-01"/>',
        )

    def test_metainfo_release_date_stamped_on_new_version(self):
        self.assertEqual(
            metainfo_release_entry("0.48.0", "0.47.0", "2026-09-01", "2026-09-13"),
            '<release version="0.48.0" date="2026-09-13"/>',
        )

    def test_metainfo_release_entry_rejects_invalid_inputs(self):
        self.assertIsNone(metainfo_release_entry("", "0.47.0", "2026-09-01", "2026-09-13"))
        self.assertIsNone(metainfo_release_entry("bogus", "0.47.0", "2026-09-01", "2026-09-13"))
        self.assertIsNone(metainfo_release_entry("0.48.0", "bogus", "2026-09-01", "2026-09-13"))
        self.assertIsNone(metainfo_release_entry("0.48.0", "0.47.0", "today", "2026-09-13"))
        self.assertIsNone(metainfo_release_entry("0.48.0", "0.47.0", "2026-09-01", "13-09-2026"))
        self.assertIsNone(metainfo_release_entry(None, "0.47.0", "2026-09-01", "2026-09-13"))
        self.assertIsNone(metainfo_release_entry("0.48.0", None, "2026-09-01", "2026-09-13"))

    def test_porcelain_allows_only_pins(self):
        self.assertTrue(porcelain_shows_only_allowed(" M data/pins.yml\n", {"data/pins.yml"}))
        self.assertTrue(porcelain_shows_only_allowed("", {"data/pins.yml"}))
        self.assertFalse(
            porcelain_shows_only_allowed(
                " M data/pins.yml\n M extra.txt\n", {"data/pins.yml"}
            )
        )
        triple_output = (
            " M data/pins.yml\n"
            " M io.github.viniciosrab.GrokBot.yml\n"
            " M data/io.github.viniciosrab.GrokBot.metainfo.xml\n"
        )
        self.assertTrue(porcelain_shows_only_allowed(triple_output, ALLOWED_PIN_PATHS))
        self.assertFalse(
            porcelain_shows_only_allowed(
                triple_output + " M extra.txt\n", ALLOWED_PIN_PATHS
            )
        )


class ShellSafetyHelperTests(unittest.TestCase):
    def test_composed_feed_args_rejected(self):
        for bad in (
            "VERSION=${{ steps.feed.outputs.version }}\necho hi",
            "curl `echo ${URL}`",
            "eval curl \"$URL\"",
            "echo ${{ needs.build.outputs.sha }}",
        ):
            self.assertFalse(run_block_is_shell_safe(bad), bad)

    def test_quoted_env_and_file_flows_accepted(self):
        good = (
            'set -euo pipefail\nVERSION="$(cat "${GITHUB_WORKSPACE}/.pin/version")"\n'
            'curl -sSL -o out.bin "${ARTIFACT_URL}"\n'
            "python3 - <<'EOF'\nprint('safe')\nEOF\n"
        )
        self.assertTrue(run_block_is_shell_safe(good))


# ---------------------------------------------------------------------------
# Repo-content contracts: RED until task 2.1 lands data/pins.yml + pin.yml.
# ---------------------------------------------------------------------------

class PinsFileContractTests(unittest.TestCase):
    def test_pins_file_exists_and_validates(self):
        self.assertTrue(os.path.isfile(PINS_PATH), "data/pins.yml must exist")
        errors = validate_pins_schema(load_pins())
        self.assertEqual(errors, [], f"pins schema violations: {errors}")

    def test_pins_feeds_are_only_sand_feeds(self):
        pins = load_pins()
        feeds = {
            arch: entry["feed"]
            for arch, entry in pins["architectures"].items()
        }
        self.assertEqual(
            feeds, {"x86_64": FEED_X64, "aarch64": FEED_ARM64}
        )
        raw = read_text(PINS_PATH)
        self.assertNotIn("x.ai/bot", raw)

    def test_pins_digests_are_real_checksums(self):
        pins = load_pins()
        for arch, entry in pins["architectures"].items():
            self.assertTrue(is_hex_digest(entry["sha256"]), arch)

    def test_pins_schema_rejects_docs_paths_and_changed_bytes(self):
        bad_pins = {
            "version": "0.47.0",
            "commitSha": "c1e7d7a46549956d25f53e9c0b9f59666e03aa3a",
            "architectures": {
                "x86_64": {
                    "feed": FEED_X64,
                    "url": "https://example.com/requirements.txt",
                    "sha256": "0" * 64,
                },
                "aarch64": {
                    "feed": FEED_ARM64,
                    "url": "https://example.com/guide.mdx",
                    "sha256": "1" * 64,
                },
            },
        }
        errors = validate_pins_schema(bad_pins)
        self.assertTrue(any("url must be an AppImage" in e for e in errors))


class PinWorkflowContractTests(unittest.TestCase):
    def test_pin_workflow_exists(self):
        self.assertTrue(os.path.isfile(PIN_WORKFLOW_PATH))

    def test_feeds_only_and_no_scraping(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertIn(FEED_X64, text)
        self.assertIn(FEED_ARM64, text)
        self.assertNotIn("x.ai/bot", text)

    def test_no_git_c_flag(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertNotIn("git -C", text)
        self.assertIsNone(re.search(r"\bgit\s+-C\S", text))

    def test_commit_and_add_are_path_only(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertNotIn("commit -a", text)
        self.assertNotIn("commit --all", text)
        commit_lines = [
            line.strip()
            for line in text.splitlines()
            if re.match(r"\s*git\s+commit\b", line)
        ]
        self.assertTrue(commit_lines, "pin.yml must commit the pin by path")
        for line in commit_lines:
            self.assertTrue(
                pin_commit_is_path_only(shlex.split(line)), f"unsafe commit: {line}"
            )
        add_lines = [
            line.strip()
            for line in text.splitlines()
            if re.match(r"\s*git\s+add\b", line)
        ]
        for line in add_lines:
            self.assertTrue(
                git_add_is_path_only(shlex.split(line)), f"unsafe add: {line}"
            )

    def test_only_pins_may_change(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertIn("git status --porcelain", text)
        self.assertIn("data/pins.yml", text)
        self.assertIn("io.github.viniciosrab.GrokBot.yml", text)
        self.assertIn("data/io.github.viniciosrab.GrokBot.metainfo.xml", text)
        self.assertIn("metainfo", text.lower())

    def test_push_goes_to_origin_pin_branch_only(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertNotIn("remote set-url", text)
        push_lines = [
            line.strip()
            for line in text.splitlines()
            if re.match(r"\s*git\s+", line) and re.search(r"\bpush\b", line)
        ]
        self.assertTrue(push_lines, "pin.yml must push the pin branch")
        for line in push_lines:
            self.assertIn("extraheader", line)
            self.assertIn("origin", line)
            self.assertRegex(line, r"push.*origin")
            self.assertIn('"${PIN_BRANCH}"', line)
            self.assertNotIn("HEAD:", line)
            self.assertNotRegex(line, r"--force(?!-with-lease)")
            self.assertIn("--force-with-lease", line)
        self.assertRegex(text, r'PIN_BRANCH="pin/sand-')

    def test_pin_branch_refreshes_existing_branch(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertNotIn('git ls-remote --exit-code --heads origin "${PIN_BRANCH}"', text)
        self.assertIn('git fetch origin "${PIN_BRANCH}"', text)
        self.assertIn('git checkout -B "${PIN_BRANCH}"', text)
        self.assertIn("git diff --cached --quiet", text)
        self.assertIn("--force-with-lease", text)
        self.assertIn('PR already exists for ${PIN_BRANCH}; skipping create', text)

    def test_pin_rewrites_metainfo_release(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertIn("data/io.github.viniciosrab.GrokBot.metainfo.xml", text)
        self.assertIn('<release version=', text)
        self.assertIn('git diff --quiet -- data/pins.yml io.github.viniciosrab.GrokBot.yml data/io.github.viniciosrab.GrokBot.metainfo.xml', text)

    def test_pr_create_uses_explicit_head(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertIn("gh pr create", text)
        self.assertIn("--head", text)

    def test_pin_polls_every_six_hours(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertIn('cron: "0 */6 * * *"', text)
        self.assertNotIn('cron: "0 6 * * *"', text)

    def test_pin_enables_squash_auto_merge_on_exact_pr(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertIn("gh pr merge --auto --squash", text)
        self.assertIn('"${PR_NUMBER}"', text)
        self.assertIn("--json number", text)
        merge_lines = [
            line.strip()
            for line in text.splitlines()
            if re.search(r"\bgh\s+pr\s+merge\b", line)
        ]
        self.assertTrue(merge_lines, "pin.yml must enable auto-merge on the pin PR")
        for line in merge_lines:
            self.assertIn("--auto", line)
            self.assertIn("--squash", line)
            self.assertIn('"${PR_NUMBER}"', line)
            self.assertNotIn("PIN_BRANCH", line)
            self.assertNotIn("pin/sand-", line)

    def test_pin_never_pushes_or_merges_main_directly(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertNotIn("push origin main", text)
        self.assertNotIn("refs/heads/main", text)
        self.assertNotIn("git push origin --", text)
        for line in text.splitlines():
            stripped = line.strip()
            if re.search(r"\bgh\s+pr\s+merge\b", stripped):
                self.assertIn("--auto", stripped)
                self.assertIn('"${PR_NUMBER}"', stripped)

    def test_pin_auto_merge_fails_closed_without_exact_pr(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertIn("cannot establish the exact pin PR", text)
        self.assertIn("refusing to enable auto-merge", text)
        self.assertIn("failed to enable auto-merge for the exact pin PR", text)
        self.assertIn("failing closed", text)
        self.assertIn("exit 1", text)

    def test_pin_preserves_release_date_on_same_version_repin(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertIn("existing_version", text)
        self.assertIn("existing_date", text)
        self.assertIn("existing_version == pinned_version", text)
        self.assertIn("no date churn", text)
        self.assertIn("metainfo release date is malformed", text)

    def test_pin_grants_least_pull_request_permission_at_job_scope(self):
        text = read_text(PIN_WORKFLOW_PATH)
        self.assertEqual(text.count("pull-requests: write"), 1)
        head, _, _ = text.partition("\njobs:")
        self.assertTrue(head, "pin.yml must keep a top-level permissions block")
        self.assertNotIn("pull-requests", head)

    def test_pin_approval_uses_default_token_not_app_token(self):
        text = read_text(PIN_WORKFLOW_PATH)
        approval = workflow_step_containing(text, "gh pr review --approve")
        self.assertTrue(approval, "pin.yml must have an exact-PR approval step")
        self.assertIn("github.token", approval)
        self.assertNotIn("app-token", approval)
        # The App token stays on branch push, PR creation, and auto-merge only.
        self.assertEqual(text.count("steps.app-token.outputs.token"), 2)

    def test_pin_approval_validates_exact_pr_identity(self):
        text = read_text(PIN_WORKFLOW_PATH)
        approval = workflow_step_containing(text, "gh pr review --approve")
        self.assertTrue(approval, "pin.yml must have an exact-PR approval step")
        self.assertIn("--json reviewDecision", approval)
        self.assertIn("--json state", approval)
        self.assertIn("--json headRefName", approval)
        self.assertIn("--json baseRefName", approval)
        self.assertIn("--json author", approval)
        self.assertIn("OPEN", approval)
        self.assertIn("pin/sand-${PIN_VERSION}", approval)
        self.assertIn('"main"', approval)
        self.assertIn("grok-bot-pin[bot]", approval)
        self.assertIn("app/grok-bot-pin", approval)
        self.assertIn("refusing to approve", approval)
        self.assertIn("failed to approve the exact pin PR", approval)
        self.assertIn("exit 1", approval)
        review_lines = [
            line.strip()
            for line in approval.splitlines()
            if re.search(r"\bgh\s+pr\s+review\b", line)
        ]
        self.assertTrue(review_lines, "approval must run gh pr review")
        for line in review_lines:
            self.assertIn("--approve", line)
            self.assertIn('"${PR_NUMBER}"', line)
            self.assertNotIn("PIN_BRANCH", line)
            self.assertNotIn("pin/sand-", line)

    def test_pin_pr_mutations_target_only_the_captured_number(self):
        text = read_text(PIN_WORKFLOW_PATH)
        mutation_lines = [
            line.strip()
            for line in text.splitlines()
            if re.search(r"\bgh\s+pr\s+(merge|review)\b", line)
        ]
        self.assertTrue(mutation_lines, "pin.yml must mutate PRs only via merge/review")
        for line in mutation_lines:
            self.assertIn('"${PR_NUMBER}"', line)
            self.assertNotIn("PIN_BRANCH", line)
            self.assertNotIn("pin/sand-", line)

    def test_pin_pr_create_targets_main_explicitly(self):
        text = read_text(PIN_WORKFLOW_PATH)
        create_step = workflow_step_containing(text, "gh pr create")
        self.assertTrue(create_step, "pin.yml must create the pin PR")
        create_idx = create_step.index("gh pr create")
        base_idx = create_step.index("--base main")
        self.assertGreater(
            base_idx, create_idx, "gh pr create must pin --base main explicitly"
        )

    def test_pin_merge_validates_identity_before_mutation(self):
        text = read_text(PIN_WORKFLOW_PATH)
        merge_step = workflow_step_containing(text, "gh pr merge --auto")
        self.assertTrue(merge_step, "pin.yml must enable auto-merge on the pin PR")
        ordered = [
            "cannot establish the exact pin PR; refusing to enable auto-merge",
            "invalid pin PR number; refusing to enable auto-merge",
            "--json state",
            "--json headRefName",
            "--json baseRefName",
            "--json author",
            "is not OPEN; refusing to enable auto-merge",
            "is not the expected pin branch; refusing to enable auto-merge",
            "base is not main; refusing to enable auto-merge",
            "is not the expected pin app; refusing to enable auto-merge",
            "gh pr merge --auto",
        ]
        indices = [merge_step.index(marker) for marker in ordered]
        self.assertEqual(
            indices,
            sorted(indices),
            "number checks, then identity validation, then auto-merge, in that order",
        )

    def test_pin_merge_and_approval_share_identity_requirements(self):
        text = read_text(PIN_WORKFLOW_PATH)
        merge_step = workflow_step_containing(text, "gh pr merge --auto")
        approval = workflow_step_containing(text, "gh pr review --approve")
        required = (
            "--json state",
            "--json headRefName",
            "--json baseRefName",
            "--json author",
            '"main"',
            "grok-bot-pin[bot]",
            "app/grok-bot-pin",
            "pin/sand-${PIN_VERSION}",
            "OPEN",
        )
        for marker in required:
            self.assertIn(marker, merge_step, f"merge step must check {marker}")
            self.assertIn(marker, approval, f"approval step must check {marker}")

    def test_pin_approval_noop_follows_identity_validation(self):
        text = read_text(PIN_WORKFLOW_PATH)
        approval = workflow_step_containing(text, "gh pr review --approve")
        self.assertTrue(approval, "pin.yml must have an exact-PR approval step")
        queries = ("--json state", "--json headRefName", "--json baseRefName", "--json author")
        refusals = (
            "is not OPEN; refusing to approve",
            "is not the expected pin branch; refusing to approve",
            "base is not main; refusing to approve",
            "is not the expected pin app; refusing to approve",
        )
        noop_idx = approval.index('= "APPROVED"')
        approve_idx = approval.index("gh pr review --approve")
        for marker in queries + refusals:
            self.assertLess(
                approval.index(marker),
                noop_idx,
                f"identity check must precede the APPROVED no-op: {marker}",
            )
        self.assertLess(
            noop_idx, approve_idx, "the APPROVED no-op must precede the approval mutation"
        )

    def test_run_blocks_have_no_composed_feed_args(self):
        text = read_text(PIN_WORKFLOW_PATH)
        blocks = run_blocks_of(text)
        self.assertTrue(blocks, "pin.yml must use run: blocks")
        for block in blocks:
            self.assertTrue(run_block_is_shell_safe(block), f"unsafe run block:\n{block}")

    def test_required_secrets_named_and_fail_closed(self):
        text = read_text(PIN_WORKFLOW_PATH)
        for secret in REQUIRED_PIN_SECRETS:
            self.assertIn(f"secrets.{secret}", text, secret)
        self.assertIn("Fail closed on missing secrets", text)
        self.assertIn("exit 1", text)


if __name__ == "__main__":
    unittest.main()
