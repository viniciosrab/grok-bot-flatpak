"""Immutable GitHub Actions pins contract.

Every external `uses:` reference in `.github/workflows/*.yml` must be an
immutable full 40-character lowercase commit SHA with an inline major-tag
comment (e.g. `uses: actions/checkout@<40sha> # v4`), so a moved major
tag can never silently change what CI executes.
"""

import glob
import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOWS_GLOB = os.path.join(REPO_ROOT, ".github", "workflows", "*.yml")

USES_RE = re.compile(r"^\s*uses:\s*(\S+)(?:\s+#\s*(v\d+)\s*)?$")
PINNED_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")

EXPECTED_ACTION_PINS = {
    "actions/checkout": ("11bd71901bbe5b1630ceea73d27597364c9af683", "v4"),
    "actions/create-github-app-token": (
        "d72941d797fd3113feb6b93fd0dec494b13a2547",
        "v1",
    ),
    "actions/upload-artifact": (
        "ea165f8d65b6e75b540449e92b4886f43607fa02",
        "v4",
    ),
    "actions/download-artifact": (
        "d3f86a106a0bac45b974a628896c90dbdf5c8093",
        "v4",
    ),
    "actions/upload-pages-artifact": (
        "56afc609e74202658d3ffba0e8f6dda462b719fa",
        "v3",
    ),
    "actions/deploy-pages": (
        "d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e",
        "v4",
    ),
}


def parse_uses_entries(text: str) -> list:
    """Return [(ref, comment)] for every `uses:` line in a workflow file."""
    entries = []
    for line in text.splitlines():
        match = USES_RE.match(line)
        if match:
            entries.append((match.group(1), match.group(2)))
    return entries


def is_pinned_uses(ref: object) -> bool:
    """Accept only `owner/action@<40-char lowercase SHA>` references."""
    return isinstance(ref, str) and bool(PINNED_RE.match(ref))


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class UsesPinHelperTests(unittest.TestCase):
    def test_pinned_sha_accepted(self):
        self.assertTrue(
            is_pinned_uses(
                "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"
            )
        )

    def test_floating_tags_rejected(self):
        for bad in (
            "actions/checkout@v4",
            "actions/checkout@v4.2.2",
            "actions/checkout@main",
            "actions/checkout@",
            "actions/checkout",
            "actions/checkout@11BD71901BBE5B1630CEEA73D27597364C9AF683",
            "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af68",
            "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af6833",
            "actions/checkout@xyz",
            "./local/action",
            "docker://alpine:3.21",
            "",
            None,
        ):
            self.assertFalse(is_pinned_uses(bad), repr(bad))

    def test_uses_lines_parse_ref_and_comment(self):
        entries = parse_uses_entries(
            "      - name: x\n"
            "        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4\n"
            "        uses: actions/missing-comment@0000000000000000000000000000000000000000\n"
        )
        self.assertEqual(
            entries,
            [
                (
                    "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
                    "v4",
                ),
                (
                    "actions/missing-comment@0000000000000000000000000000000000000000",
                    None,
                ),
            ],
        )


class WorkflowPinsContractTests(unittest.TestCase):
    def test_all_workflow_uses_are_immutable_shas(self):
        paths = sorted(glob.glob(WORKFLOWS_GLOB))
        self.assertEqual(len(paths), 4, "expected exactly four workflow files")
        for path in paths:
            with self.subTest(workflow=os.path.basename(path)):
                entries = parse_uses_entries(read_text(path))
                self.assertTrue(entries, f"{path} must contain uses: references")
                for ref, _comment in entries:
                    self.assertTrue(
                        is_pinned_uses(ref),
                        f"{path}: {ref} is not a full 40-char SHA pin",
                    )

    def test_every_pin_carries_its_major_tag_comment(self):
        for path in sorted(glob.glob(WORKFLOWS_GLOB)):
            with self.subTest(workflow=os.path.basename(path)):
                for ref, comment in parse_uses_entries(read_text(path)):
                    action, _, _sha = ref.partition("@")
                    expected = EXPECTED_ACTION_PINS.get(action)
                    self.assertIsNotNone(
                        expected, f"{path}: unexpected action {action}"
                    )
                    assert expected is not None
                    self.assertEqual(
                        comment,
                        expected[1],
                        f"{path}: {ref} must keep its inline {expected[1]} comment",
                    )

    def test_known_actions_resolve_to_the_recorded_shas(self):
        seen: dict = {}
        for path in sorted(glob.glob(WORKFLOWS_GLOB)):
            for ref, _comment in parse_uses_entries(read_text(path)):
                action, _, sha = ref.partition("@")
                seen.setdefault(action, set()).add(sha)
        self.assertEqual(set(seen), set(EXPECTED_ACTION_PINS))
        for action, (sha, _tag) in EXPECTED_ACTION_PINS.items():
            self.assertEqual(
                seen[action],
                {sha},
                f"{action} must resolve to exactly {sha}",
            )


if __name__ == "__main__":
    unittest.main()
