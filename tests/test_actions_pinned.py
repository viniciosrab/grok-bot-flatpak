"""Immutable GitHub Actions pins contract.

Every external `uses:` reference in `.github/workflows/*.yml` must be an
immutable full 40-character lowercase commit SHA with an inline major-tag
comment (e.g. `uses: actions/checkout@<40sha> # v4`), so a moved major
tag can never silently change what CI executes.
"""

import glob
import os
import re
import subprocess
import textwrap
import unittest

from tools.validate_dependabot_actions import ValidationError, validate

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOWS_GLOB = os.path.join(REPO_ROOT, ".github", "workflows", "*.yml")
DEPENDABOT_PATH = os.path.join(REPO_ROOT, ".github", "dependabot.yml")
DEPENDABOT_AUTOMERGE_PATH = os.path.join(
    REPO_ROOT, ".github", "workflows", "dependabot-automerge.yml"
)

USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)(?:\s+#\s*(v\d+)\s*)?$")
USES_KEY_RE = re.compile(r"^\s*(?:-\s+)?uses\s*:")
PINNED_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")

EXPECTED_ACTION_MAJORS = {
    "actions/checkout": "v4",
    "actions/create-github-app-token": "v1",
    "actions/upload-artifact": "v4",
    "actions/download-artifact": "v4",
    "actions/upload-pages-artifact": "v3",
    "actions/deploy-pages": "v4",
}


def parse_uses_entries(text: str) -> list:
    """Return [(ref, comment)] for every `uses:` line in a workflow file."""
    entries = []
    for line in text.splitlines():
        if not USES_KEY_RE.match(line):
            continue
        match = USES_RE.fullmatch(line)
        if not match:
            raise ValueError("malformed uses line: %s" % line)
        entries.append((match.group(1), match.group(2)))
    return entries


def is_pinned_uses(ref: object) -> bool:
    """Accept only `owner/action@<40-char lowercase SHA>` references."""
    return isinstance(ref, str) and bool(PINNED_RE.fullmatch(ref))


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
            "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683\n",
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
            "        - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4\n"
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

    def test_malformed_uses_lines_are_not_ignored(self):
        for line in (
            "        uses: actions/checkout@v4 # v4",
            "        uses: actions/checkout@" + "a" * 39 + " # v4",
            "        uses: actions/checkout@" + "A" * 40 + " # v4",
            "        uses: actions/checkout@" + "a" * 40 + " # v5 extra",
        ):
            try:
                entries = parse_uses_entries(line)
            except ValueError:
                continue
            self.assertEqual(len(entries), 1)
            self.assertFalse(is_pinned_uses(entries[0][0]))


class DependabotConfigContractTests(unittest.TestCase):
    def test_dependabot_updates_only_allowlisted_actions(self):
        text = read_text(DEPENDABOT_PATH)
        self.assertRegex(text, r"(?m)^version:\s*2\s*$")
        self.assertEqual(text.count('package-ecosystem: "github-actions"'), 1)
        self.assertIn('directory: "/"', text)
        self.assertIn('interval: "weekly"', text)
        self.assertIn("open-pull-requests-limit: 3", text)

        allow_section = text.split("    allow:\n", 1)[1].split(
            "    ignore:\n", 1
        )[0]
        allowed = set(
            re.findall(
                r'(?m)^\s+- dependency-name: "([^\"]+)"\s*$',
                allow_section,
            )
        )
        self.assertEqual(allowed, set(EXPECTED_ACTION_MAJORS))

    def test_dependabot_keeps_major_upgrades_manual(self):
        text = read_text(DEPENDABOT_PATH)
        ignore_section = text.split("    ignore:\n", 1)[1]
        self.assertIn('dependency-name: "*"', ignore_section)
        self.assertIn('"version-update:semver-major"', ignore_section)
        self.assertNotIn("automerge", text.lower())


class WorkflowPinsContractTests(unittest.TestCase):
    def test_all_workflow_uses_are_immutable_shas(self):
        paths = sorted(glob.glob(WORKFLOWS_GLOB))
        self.assertEqual(len(paths), 5, "expected exactly five workflow files")
        for path in paths:
            with self.subTest(workflow=os.path.basename(path)):
                entries = parse_uses_entries(read_text(path))
                if os.path.basename(path) != "dependabot-automerge.yml":
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
                    expected = EXPECTED_ACTION_MAJORS.get(action)
                    self.assertIsNotNone(
                        expected, f"{path}: unexpected action {action}"
                    )
                    assert expected is not None
                    self.assertEqual(
                        comment,
                        expected,
                        f"{path}: {ref} must keep its inline {expected} comment",
                    )

    def test_workflows_use_only_the_allowlisted_actions(self):
        seen: dict = {}
        for path in sorted(glob.glob(WORKFLOWS_GLOB)):
            for ref, _comment in parse_uses_entries(read_text(path)):
                action, _, sha = ref.partition("@")
                seen.setdefault(action, set()).add(sha)
        self.assertEqual(set(seen), set(EXPECTED_ACTION_MAJORS))
        for action in EXPECTED_ACTION_MAJORS:
            self.assertTrue(seen[action], f"{action} must be used by a workflow")


def run_automerge_validator(
    pr: dict, files: list, event_number: str = "17", compare=None
) -> tuple[bool, dict]:
    if compare is None:
        compare = {
            "base_commit": {"sha": "a" * 40},
            "head_commit": {"sha": "b" * 40},
            "status": "ahead",
            "total_commits": 1,
            "commits": [{"sha": "b" * 40}],
            "files": files,
        }
    try:
        result = validate(
            pr,
            compare,
            event_number,
            "a" * 40,
            "b" * 40,
            pr.get("head", {}).get(
                "ref", "dependabot/github_actions/actions/checkout-4.2.2"
            ),
        )
    except ValidationError as error:
        return False, {"error": str(error)}
    return True, result


def valid_dependabot_pr() -> dict:
    return {
        "number": 17,
        "state": "open",
        "draft": False,
        "changed_files": 1,
        "additions": 1,
        "deletions": 1,
        "user": {"login": "dependabot[bot]"},
        "base": {
            "ref": "main",
            "sha": "a" * 40,
            "repo": {"full_name": "viniciosrab/grok-bot-flatpak"},
        },
        "head": {
            "ref": "dependabot/github_actions/actions/checkout-4.2.2",
            "sha": "b" * 40,
            "repo": {"full_name": "viniciosrab/grok-bot-flatpak"},
        },
    }


def valid_action_patch() -> dict:
    return {
        "filename": ".github/workflows/validate.yml",
        "status": "modified",
        "additions": 1,
        "deletions": 1,
        "changes": 2,
        "patch": (
            "@@ -32,1 +32,1 @@\n"
            "-        uses: actions/checkout@" + "a" * 40 + " # v4\n"
            "+        uses: actions/checkout@" + "b" * 40 + " # v4\n"
        ),
    }


def classify_validator_output(content: str, pr: str = "17", base: str = "a" * 40,
                              head: str = "b" * 40,
                              ref: str = "dependabot/github_actions/actions/checkout-4.2.2") -> str:
    lines = content.splitlines()
    expected_true = [
        "eligible=true",
        "pr_number=" + pr,
        "base_oid=" + base,
        "head_oid=" + head,
        "head_ref=" + ref,
    ]
    expected_false = list(expected_true)
    expected_false[0] = "eligible=false"
    if lines == expected_false:
        return "draft"
    if lines != expected_true:
        raise ValueError("validator output is missing, duplicated, or malformed")
    return "eligible"


class ValidationOutputContractTests(unittest.TestCase):
    def test_exact_eligible_true_output_is_required(self):
        output = (
            "eligible=true\n"
            "pr_number=17\n"
            "base_oid=" + "a" * 40 + "\n"
            "head_oid=" + "b" * 40 + "\n"
            "head_ref=dependabot/github_actions/actions/checkout-4.2.2\n"
        )
        self.assertEqual(classify_validator_output(output), "eligible")

    def test_draft_output_stops_without_mutation(self):
        output = (
            "eligible=false\n"
            "pr_number=17\n"
            "base_oid=" + "a" * 40 + "\n"
            "head_oid=" + "b" * 40 + "\n"
            "head_ref=dependabot/github_actions/actions/checkout-4.2.2\n"
        )
        self.assertEqual(classify_validator_output(output), "draft")

    def test_missing_duplicate_and_malformed_outputs_fail_closed(self):
        valid = (
            "eligible=true\n"
            "pr_number=17\n"
            "base_oid=" + "a" * 40 + "\n"
            "head_oid=" + "b" * 40 + "\n"
            "head_ref=dependabot/github_actions/actions/checkout-4.2.2\n"
        )
        cases = (
            valid.replace("head_oid=" + "b" * 40 + "\n", ""),
            valid + "eligible=true\n",
            valid.replace("eligible=true", "eligible=TRUE"),
            valid.replace("head_ref=dependabot/", "head_ref=attacker/"),
            valid + "unexpected=value\n",
        )
        for case in cases:
            with self.assertRaises(ValueError):
                classify_validator_output(case)


class DependabotAutomergeWorkflowTests(unittest.TestCase):
    def test_workflow_uses_trusted_target_and_restricted_triggers(self):
        text = read_text(DEPENDABOT_AUTOMERGE_PATH)
        self.assertIn("pull_request_target:", text)
        for event in ("opened", "reopened", "synchronize", "ready_for_review"):
            self.assertIn(event, text)
        self.assertNotIn("workflow_dispatch", text)
        self.assertNotIn("inputs:", text)
        self.assertIn("viniciosrab/grok-bot-flatpak", text)
        self.assertIn("dependabot[bot]", text)
        self.assertIn("base.ref", text)
        self.assertIn('"main"', text)

    def test_workflow_never_checks_out_or_executes_pr_bytes(self):
        text = read_text(DEPENDABOT_AUTOMERGE_PATH)
        self.assertNotIn("actions/checkout@", text)
        self.assertNotIn("gh pr checkout", text)
        self.assertNotIn("git checkout", text)
        self.assertNotIn("github.event.pull_request.head.sha", text)
        self.assertNotIn("github.event.pull_request.head.ref", text)
        self.assertNotIn("flatpak-builder", text)
        self.assertNotIn("dependabot/fetch-metadata", text)
        self.assertNotIn("eval ", text)
        run_blocks = re.findall(
            r"(?ms)^        run: \|\n(.*?)(?=^\s{6}- name:|\Z)", text
        )
        self.assertTrue(run_blocks)
        for block in run_blocks:
            self.assertNotIn("${{", block)

    def test_each_real_yaml_shell_block_passes_bash_n(self):
        text = read_text(DEPENDABOT_AUTOMERGE_PATH)
        lines = text.splitlines()
        blocks = []
        index = 0
        while index < len(lines):
            if lines[index] != "        run: |":
                index += 1
                continue
            index += 1
            block = []
            while index < len(lines):
                line = lines[index]
                indent = len(line) - len(line.lstrip(" "))
                if line.strip() and indent <= 8:
                    break
                block.append(line)
                index += 1
            blocks.append(textwrap.dedent("\n".join(block)) + "\n")
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            result = subprocess.run(
                ["bash", "-n"], input=block, text=True, capture_output=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_workflow_has_least_privilege_and_existing_app_pin(self):
        text = read_text(DEPENDABOT_AUTOMERGE_PATH)
        self.assertIn("permissions:\n  contents: write\n  pull-requests: write", text)
        self.assertIn("GH_TOKEN: ${{ github.token }}", text)
        self.assertNotIn("actions/create-github-app-token@", text)
        self.assertNotIn("secrets.APP_ID", text)
        self.assertNotIn("secrets.APP_PRIVATE_KEY", text)
        self.assertNotIn("permission-pull-requests", text)
        self.assertIn("Allow GitHub Actions to create and approve pull requests", text)

    def test_foreign_synchronize_cancels_only_the_exact_dependabot_pr(self):
        text = read_text(DEPENDABOT_AUTOMERGE_PATH)
        for marker in (
            'if [ "${EVENT_ACTION}" = "synchronize" ]',
            '[ "${EVENT_SENDER}" != "dependabot[bot]" ]',
            '[ "${EVENT_REPOSITORY}" != "${EXPECTED_REPOSITORY}" ]',
            '[ "${PR_NUMBER}" -le 0 ]',
            'pr.get("number") != int(os.environ["EVENT_PR_NUMBER"])',
            'user.get("login") != "dependabot[bot]"',
            'base.get("ref") != "main"',
            'base_repo.get("full_name") != expected_repo',
            'gh api "repos/${EXPECTED_REPOSITORY}/pulls/${PR_NUMBER}"',
            'CANCEL_HEAD_OID',
            '--disable-auto',
            '--match-head-commit "${CANCEL_HEAD_OID}" "${PR_NUMBER}"',
            'failed to disable stale auto-merge; failing closed',
        ):
            self.assertIn(marker, text, marker)
        self.assertLess(text.index('base.get("ref") != "main"'), text.index("--disable-auto"))
        self.assertLess(text.index('CANCEL_HEAD_OID="$(cat'), text.index("--disable-auto"))

    def test_each_revalidation_requires_exact_output_before_mutation(self):
        text = read_text(DEPENDABOT_AUTOMERGE_PATH)
        for marker in (
            'require_exact_validation_output()',
            'PRE_VALIDATION_OUTPUT="${RUNNER_TEMP}/dependabot-validation-pre-approval.out"',
            'FINAL_VALIDATION_OUTPUT="${RUNNER_TEMP}/dependabot-validation-final.out"',
            'validator output is missing, duplicated, or malformed',
            'PRE_VALIDATION_STATUS',
            'FINAL_VALIDATION_STATUS',
            'PR became draft during pre-approval revalidation; no mutation',
            'PR became draft during final revalidation; no merge mutation',
            'pre-approval validator output was not exactly eligible=true; refusing mutation',
            'final validator output was not exactly eligible=true; refusing merge',
        ):
            self.assertIn(marker, text, marker)
        approval = text.index('gh api --method POST "repos/${EXPECTED_REPOSITORY}/pulls/${PR_NUMBER}/reviews"')
        merge = text.index('gh pr merge --repo "${EXPECTED_REPOSITORY}" --auto --squash')
        self.assertLess(text.index('PRE_VALIDATION_OUTPUT', text.index('run: |', text.index('Revalidate'))), approval)
        self.assertLess(text.index('FINAL_VALIDATION_OUTPUT'), merge)
        self.assertEqual(text.count('GITHUB_OUTPUT="${PRE_VALIDATION_OUTPUT}" python3'), 1)
        self.assertEqual(text.count('GITHUB_OUTPUT="${FINAL_VALIDATION_OUTPUT}" python3'), 1)

    def test_workflow_validates_paths_patch_metadata_and_merge_binding(self):
        text = read_text(DEPENDABOT_AUTOMERGE_PATH)
        helper = read_text(os.path.join(REPO_ROOT, "tools", "validate_dependabot_actions.py"))
        for marker in (
            "/compare/${BASE_OID}...${HEAD_OID}",
            "contents/tools/validate_dependabot_actions.py?ref=${BASE_OID}",
            "EXPECTED_BASE_OID",
            "EXPECTED_HEAD_OID",
            "EXPECTED_HEAD_REF",
            'EVENT_SENDER: ${{ github.event.sender.login }}',
            'EVENT_AUTHOR: ${{ github.event.pull_request.user.login }}',
            'response.get("sha") != blob_sha',
            'gh api --method POST "repos/${EXPECTED_REPOSITORY}/pulls/${PR_NUMBER}/reviews"',
            "-f commit_id=\"${EXPECTED_HEAD_OID}\"",
        ):
            self.assertIn(marker, text, marker)
        for marker in (
            'base_commit.get("sha") != expected_base_oid',
            'head_commit.get("sha") != expected_head_oid',
            'commits[-1]["sha"] != expected_head_oid',
            r'FILE_RE = re.compile(r"^\.github/workflows/[^/]+\.yml$")',
            'item.get("status") != "modified"',
            '"previous_filename" in item',
            'item.get("patch")',
            "patch hunk line counts are incomplete or truncated",
            "patch line counts do not match API metadata",
            "file list is incomplete or inconsistent with the PR metadata",
            "PR change totals are malformed",
            "file change totals are inconsistent with the PR metadata",
            "only paired uses lines may change",
            "Action identity changed instead of only its SHA",
            "Action comment changed instead of only its SHA",
            "changed Action is not allowlisted",
        ):
            self.assertIn(marker, helper, marker)
        self.assertNotIn("--admin", text)
        self.assertIn('gh pr merge --repo "${EXPECTED_REPOSITORY}" --auto --squash \\', text)
        self.assertIn('--match-head-commit "${EXPECTED_HEAD_OID}" "${PR_NUMBER}"', text)

    def test_main_capture_bootstrap_stays_minimal(self):
        text = read_text(DEPENDABOT_AUTOMERGE_PATH)
        helper = read_text(os.path.join(REPO_ROOT, "tools", "validate_dependabot_actions.py"))
        self.assertIn("Full Dependabot identity", text)
        blocks = text.split("<<'PYEOF'")
        capture = None
        for part in blocks[1:]:
            body = part.split("PYEOF", 1)[0]
            if "(base_oid, head_oid, head_ref)" in body:
                capture = body
                break
        self.assertIsNotNone(capture, "main capture bootstrap must exist")
        assert capture is not None
        for marker in (
            "pull request base repository is not exact",
            "pull request base is not main",
            "pull request base OID is not a full lowercase SHA",
            "pull request head OID is not a full lowercase SHA",
        ):
            self.assertIn(marker, capture, marker)
        for absent in (
            "dependabot[bot]",
            "allowlisted Action",
            "expected Dependabot branch",
            "is not open",
            "draft",
            "ACTIONS",
            "HEAD_RE",
        ):
            self.assertNotIn(absent, capture, absent)
        for marker in (
            "pull request author is not exactly dependabot[bot]",
            "pull request is not open; refusing auto-merge",
            "pull request head does not identify an allowlisted Action",
            "draft state is missing or malformed",
        ):
            self.assertIn(marker, helper, marker)

    def test_valid_hostile_boundary_fixture_is_accepted(self):
        ok, result = run_automerge_validator(
            valid_dependabot_pr(), [valid_action_patch()]
        )
        self.assertTrue(ok, result)
        self.assertTrue(result["eligible"])
        self.assertEqual(result["head_oid"], "b" * 40)

    def test_identity_fixtures_are_rejected(self):
        cases = []
        for field, value in (
            ("user", {"login": "octocat"}),
            ("base", {"ref": "develop", "repo": {"full_name": "viniciosrab/grok-bot-flatpak"}}),
            ("head", {"ref": "feature/checkout", "sha": "b" * 40, "repo": {"full_name": "viniciosrab/grok-bot-flatpak"}}),
        ):
            pr = valid_dependabot_pr()
            pr[field] = value
            cases.append(pr)
        foreign_head = valid_dependabot_pr()
        foreign_head["head"]["repo"] = {"full_name": "attacker/example"}
        cases.append(foreign_head)
        malformed_oid = valid_dependabot_pr()
        malformed_oid["head"]["sha"] = "B" * 40
        cases.append(malformed_oid)
        for pr in cases:
            ok, _result = run_automerge_validator(pr, [valid_action_patch()])
            self.assertFalse(ok, pr)

    def test_draft_is_a_no_mutation_success(self):
        pr = valid_dependabot_pr()
        pr["draft"] = True
        ok, result = run_automerge_validator(pr, [valid_action_patch()])
        self.assertTrue(ok, result)
        self.assertFalse(result["eligible"])

    def test_hostile_path_and_file_status_fixtures_are_rejected(self):
        for change in (
            dict(valid_action_patch(), filename=".github/workflows/../evil.yml"),
            dict(valid_action_patch(), filename=".github/workflows/evil.yaml"),
            dict(valid_action_patch(), status="added"),
            dict(valid_action_patch(), previous_filename=".github/workflows/old.yml"),
            dict(valid_action_patch(), patch=None),
            dict(valid_action_patch(), additions=2),
            dict(valid_action_patch(), deletions=2),
            dict(valid_action_patch(), changes=True),
        ):
            ok, _result = run_automerge_validator(
                valid_dependabot_pr(), [change]
            )
            self.assertFalse(ok, change)

    def test_hostile_diff_line_fixtures_are_rejected(self):
        cases = []
        non_uses = dict(valid_action_patch())
        non_uses["patch"] = "@@ -1,1 +1,1 @@\n-old\n+new\n"
        cases.append(non_uses)
        changed_action = dict(valid_action_patch())
        changed_action["patch"] = (
            "@@ -1,1 +1,1 @@\n"
            "-        uses: actions/checkout@" + "a" * 40 + " # v4\n"
            "+        uses: actions/upload-artifact@" + "b" * 40 + " # v4\n"
        )
        cases.append(changed_action)
        changed_comment = dict(valid_action_patch())
        changed_comment["patch"] = changed_comment["patch"].replace("# v4", "# v3")
        cases.append(changed_comment)
        uppercase_sha = dict(valid_action_patch())
        uppercase_sha["patch"] = uppercase_sha["patch"].replace("b" * 40, "B" * 40)
        cases.append(uppercase_sha)
        unauthorized_major = dict(valid_action_patch())
        unauthorized_major["patch"] = unauthorized_major["patch"].replace(
            "# v4", "# v5"
        )
        cases.append(unauthorized_major)
        truncated = dict(valid_action_patch())
        truncated["patch"] = (
            "@@ -32,2 +32,2 @@\n"
            "-        uses: actions/checkout@" + "a" * 40 + " # v4\n"
            "+        uses: actions/checkout@" + "b" * 40 + " # v4\n"
        )
        cases.append(truncated)
        too_large = dict(valid_action_patch(), patch="x" * 20000)
        cases.append(too_large)
        unpaired = dict(valid_action_patch())
        unpaired["additions"] = 2
        unpaired["changes"] = 3
        unpaired["patch"] = (
            "@@ -1,1 +1,2 @@\n"
            "-        uses: actions/checkout@" + "a" * 40 + " # v4\n"
            "+        uses: actions/checkout@" + "b" * 40 + " # v4\n"
            "+        run: hostile\n"
        )
        cases.append(unpaired)
        for change in cases:
            ok, _result = run_automerge_validator(
                valid_dependabot_pr(), [change]
            )
            self.assertFalse(ok, change)

    def test_exact_no_newline_marker_does_not_change_counts(self):
        change = valid_action_patch()
        change["patch"] = (
            change["patch"].rstrip("\n")
            + "\n\\ No newline at end of file\n"
        )
        ok, result = run_automerge_validator(valid_dependabot_pr(), [change])
        self.assertTrue(ok, result)

    def test_malformed_no_newline_marker_is_rejected(self):
        change = valid_action_patch()
        change["patch"] = change["patch"].replace(
            "@@ -32,1 +32,1 @@",
            "@@ -32,1 +32,1 @@\n\\ No newline at end of file ",
        )
        ok, _result = run_automerge_validator(valid_dependabot_pr(), [change])
        self.assertFalse(ok)

    def test_compare_response_is_bound_to_base_and_final_commit_oids(self):
        for field, value in (
            ("base_commit", {"sha": "c" * 40}),
            ("commits", [{"sha": "c" * 40}]),
        ):
            compare = {
                "base_commit": {"sha": "a" * 40},
                "head_commit": {"sha": "b" * 40},
                "status": "ahead",
                "total_commits": 1,
                "commits": [{"sha": "b" * 40}],
                "files": [valid_action_patch()],
            }
            compare[field] = value
            ok, _result = run_automerge_validator(
                valid_dependabot_pr(), [valid_action_patch()], compare=compare
            )
            self.assertFalse(ok, field)

    def test_compare_head_commit_oid_is_bound_to_captured_head(self):
        hostile_heads = (
            {"sha": "c" * 40},
            {"sha": "B" * 40},
            {"sha": ""},
            {},
            None,
            "b" * 40,
        )
        for head_commit in hostile_heads:
            compare = {
                "base_commit": {"sha": "a" * 40},
                "head_commit": head_commit,
                "status": "ahead",
                "total_commits": 1,
                "commits": [{"sha": "b" * 40}],
                "files": [valid_action_patch()],
            }
            ok, _result = run_automerge_validator(
                valid_dependabot_pr(), [valid_action_patch()], compare=compare
            )
            self.assertFalse(ok, head_commit)
        missing = {
            "base_commit": {"sha": "a" * 40},
            "status": "ahead",
            "total_commits": 1,
            "commits": [{"sha": "b" * 40}],
            "files": [valid_action_patch()],
        }
        ok, _result = run_automerge_validator(
            valid_dependabot_pr(), [valid_action_patch()], compare=missing
        )
        self.assertFalse(ok)

    def test_event_number_is_bound_to_the_api_pr(self):
        ok, _result = run_automerge_validator(
            valid_dependabot_pr(), [valid_action_patch()], event_number="18"
        )
        self.assertFalse(ok)

    def test_mutations_revalidate_and_bind_the_captured_oid(self):
        text = read_text(DEPENDABOT_AUTOMERGE_PATH)
        mutation = text.index("Revalidate the exact head, approve")
        merge = text.index('gh pr merge --repo "${EXPECTED_REPOSITORY}" --auto --squash')
        self.assertLess(text.index("python3 \"${VALIDATOR_PATH}\"", mutation), merge)
        self.assertLess(text.index("FINAL_PR", mutation), merge)
        self.assertIn('head.get("sha")', read_text(os.path.join(REPO_ROOT, "tools", "validate_dependabot_actions.py")))
        self.assertIn('review.get("commit_id") == os.environ["EXPECTED_HEAD_OID"]', text)
        self.assertIn('review.get("commit_id") != os.environ["EXPECTED_HEAD_OID"]', text)


if __name__ == "__main__":
    unittest.main()
