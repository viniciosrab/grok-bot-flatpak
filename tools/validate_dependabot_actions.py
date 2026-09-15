"""Validate a Dependabot GitHub Actions PR from API JSON only.

The caller must obtain the PR response and compare response from the exact
captured base/head OIDs. This module never reads a checkout or executes PR
content; patches are parsed as untrusted data.
"""

import json
import os
import re
import sys


ACTION_MAJORS = {
    "actions/checkout": "v4",
    "actions/create-github-app-token": "v1",
    "actions/upload-artifact": "v4",
    "actions/download-artifact": "v4",
    "actions/upload-pages-artifact": "v3",
    "actions/deploy-pages": "v4",
}
EXPECTED_REPOSITORY = "viniciosrab/grok-bot-flatpak"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
FILE_RE = re.compile(r"^\.github/workflows/[^/]+\.yml$")
HEAD_RE = re.compile(
    r"^dependabot/github_actions/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+-[0-9][A-Za-z0-9_.-]*$"
)
HUNK_RE = re.compile(
    r"^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@(?: .*)?$"
)
USES_RE = re.compile(
    r"^(?P<prefix>\s*(?:-\s+)?uses:\s*"
    r"(?P<action>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@)"
    r"(?P<sha>[0-9a-f]{40})"
    r"(?P<suffix>\s+#\s*v[0-9]+\s*)$"
)
NO_NEWLINE_MARKER = r"\ No newline at end of file"


class ValidationError(ValueError):
    """A fail-closed API or diff contract violation."""


def reject(message: str) -> None:
    raise ValidationError(message)


def load_json(path: str):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as error:
        reject("invalid GitHub API JSON: %s" % error)


def validate_head_ref(head_ref: object) -> str:
    if not isinstance(head_ref, str) or not HEAD_RE.fullmatch(head_ref):
        reject("pull request head is not an expected Dependabot branch")
    prefix = "dependabot/github_actions/"
    action = head_ref[len(prefix):]
    if not any(
        action == allowed or action.startswith(allowed + "-")
        for allowed in ACTION_MAJORS
    ):
        reject("pull request head does not identify an allowlisted Action")
    return head_ref


def validate_identity(
    pr: dict,
    event_number: str,
    expected_base_oid: str,
    expected_head_oid: str,
    expected_head_ref: str,
    expected_repository: str = EXPECTED_REPOSITORY,
) -> dict:
    if not event_number.isdigit() or int(event_number) <= 0:
        reject("event pull request number is malformed")
    if not isinstance(pr, dict):
        reject("pull request response is not an object")
    if isinstance(pr.get("number"), bool) or not isinstance(pr.get("number"), int):
        reject("pull request number is malformed")
    if pr["number"] != int(event_number):
        reject("API pull request number differs from the event number")
    if pr.get("state") != "open":
        reject("pull request is not open; refusing auto-merge")
    user = pr.get("user")
    if not isinstance(user, dict) or user.get("login") != "dependabot[bot]":
        reject("pull request author is not exactly dependabot[bot]")

    base = pr.get("base")
    head = pr.get("head")
    if not isinstance(base, dict) or not isinstance(head, dict):
        reject("pull request base/head metadata is malformed")
    base_repo = base.get("repo")
    head_repo = head.get("repo")
    if not isinstance(base_repo, dict) or not isinstance(head_repo, dict):
        reject("pull request base/head repository metadata is malformed")
    if base_repo.get("full_name") != expected_repository:
        reject("pull request base repository is not exact")
    if head_repo.get("full_name") != expected_repository:
        reject("pull request head repository is not exact")
    if base.get("ref") != "main":
        reject("pull request base is not main")

    if not COMMIT_RE.fullmatch(expected_base_oid or ""):
        reject("expected base OID is malformed")
    if not COMMIT_RE.fullmatch(expected_head_oid or ""):
        reject("expected head OID is malformed")
    if base.get("sha") != expected_base_oid:
        reject("pull request base OID differs from the captured OID")
    if head.get("sha") != expected_head_oid:
        reject("pull request head OID differs from the captured OID")
    if not isinstance(expected_head_ref, str):
        reject("expected head ref is malformed")
    if head.get("ref") != expected_head_ref:
        reject("pull request head ref differs from the captured ref")
    validate_head_ref(head.get("ref"))

    draft = pr.get("draft")
    if draft is True:
        return {
            "eligible": False,
            "base_oid": expected_base_oid,
            "head_oid": expected_head_oid,
            "head_ref": expected_head_ref,
        }
    if draft is not False:
        reject("draft state is missing or malformed")
    return {
        "eligible": True,
        "base_oid": expected_base_oid,
        "head_oid": expected_head_oid,
        "head_ref": expected_head_ref,
    }


def validate_changed_block(old_changed: list, new_changed: list) -> None:
    if not old_changed and not new_changed:
        return
    if len(old_changed) != len(new_changed):
        reject("changed lines are not paired uses lines")
    for old_line, new_line in zip(old_changed, new_changed):
        old_match = USES_RE.fullmatch(old_line)
        new_match = USES_RE.fullmatch(new_line)
        if not old_match or not new_match:
            reject("only paired uses lines may change")
        if old_match.group("prefix") != new_match.group("prefix"):
            reject("Action identity changed instead of only its SHA")
        if old_match.group("suffix") != new_match.group("suffix"):
            reject("Action comment changed instead of only its SHA")
        action = old_match.group("action")
        if action not in ACTION_MAJORS:
            reject("changed Action is not allowlisted")
        comment_match = re.fullmatch(r"\s+#\s*(v[0-9]+)\s*", old_match.group("suffix"))
        if not comment_match or comment_match.group(1) != ACTION_MAJORS[action]:
            reject("changed Action major comment is not authorized")
        if old_match.group("sha") == new_match.group("sha"):
            reject("changed uses pair has no SHA change")


def validate_file(item: dict) -> tuple[int, int]:
    filename = item.get("filename")
    if not isinstance(filename, str) or not FILE_RE.fullmatch(filename):
        reject("changed path is outside .github/workflows/*.yml")
    if item.get("status") != "modified":
        reject("added, removed, renamed, or copied files are forbidden")
    if "previous_filename" in item:
        reject("rename metadata is forbidden")

    patch = item.get("patch")
    if not isinstance(patch, str) or not patch:
        reject("patch is absent; refusing to validate an incomplete diff")
    if len(patch) >= 20000:
        reject("patch may be truncated; refusing to validate it")
    if "\r" in patch:
        reject("patch has ambiguous line endings")

    additions = item.get("additions")
    deletions = item.get("deletions")
    changes = item.get("changes")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (additions, deletions, changes)
    ):
        reject("file change metadata is malformed")
    if changes != additions + deletions:
        reject("file change metadata counts are inconsistent")

    patch_additions = 0
    patch_deletions = 0
    saw_hunk = False
    old_count = new_count = None
    old_used = new_used = 0
    old_changed = []
    new_changed = []

    def finish_hunk() -> None:
        nonlocal old_count, new_count, old_used, new_used
        validate_changed_block(old_changed, new_changed)
        if old_count is None or new_count is None:
            return
        if old_used != old_count or new_used != new_count:
            reject("patch hunk line counts are incomplete or truncated")

    for line in patch.splitlines():
        if line == NO_NEWLINE_MARKER:
            if not saw_hunk:
                reject("newline marker appears outside a patch hunk")
            continue
        if line.startswith("@@"):
            if saw_hunk:
                finish_hunk()
            match = HUNK_RE.fullmatch(line)
            if not match:
                reject("malformed patch hunk header")
            old_count = int(match.group(2) or "1")
            new_count = int(match.group(4) or "1")
            old_used = new_used = 0
            old_changed = []
            new_changed = []
            saw_hunk = True
            continue
        if not saw_hunk:
            reject("patch is missing a valid hunk")
        if line.startswith("+"):
            new_used += 1
            patch_additions += 1
            new_changed.append(line[1:])
        elif line.startswith("-"):
            old_used += 1
            patch_deletions += 1
            old_changed.append(line[1:])
        elif line.startswith(" "):
            old_used += 1
            new_used += 1
            validate_changed_block(old_changed, new_changed)
            old_changed = []
            new_changed = []
        else:
            reject("patch contains a non-unified-diff line")

    if not saw_hunk:
        reject("patch has no hunks")
    finish_hunk()
    if patch_additions != additions or patch_deletions != deletions:
        reject("patch line counts do not match API metadata")
    if changes != patch_additions + patch_deletions:
        reject("patch changes do not match API metadata")
    if patch_additions == 0 or patch_deletions == 0:
        reject("every change must be a paired replacement")
    return additions, deletions


def validate_compare(
    compare: dict,
    pr: dict,
    expected_base_oid: str,
    expected_head_oid: str,
) -> None:
    if not isinstance(compare, dict):
        reject("compare response is not an object")
    base_commit = compare.get("base_commit")
    if not isinstance(base_commit, dict) or base_commit.get("sha") != expected_base_oid:
        reject("compare response base OID is not the captured base OID")
    commits = compare.get("commits")
    total_commits = compare.get("total_commits")
    if (
        not isinstance(commits, list)
        or isinstance(total_commits, bool)
        or not isinstance(total_commits, int)
        or total_commits != len(commits)
        or not commits
    ):
        reject("compare commit list is incomplete or malformed")
    for commit in commits:
        if not isinstance(commit, dict) or not COMMIT_RE.fullmatch(commit.get("sha", "")):
            reject("compare response contains a malformed commit OID")
    if commits[-1]["sha"] != expected_head_oid:
        reject("compare response head commit is not the captured head OID")

    files = compare.get("files")
    if not isinstance(files, list) or not files:
        reject("compare response has no complete file list")
    changed_files = pr.get("changed_files")
    if (
        isinstance(changed_files, bool)
        or not isinstance(changed_files, int)
        or changed_files != len(files)
    ):
        reject("file list is incomplete or inconsistent with the PR metadata")
    total_additions = 0
    total_deletions = 0
    for item in files:
        if not isinstance(item, dict):
            reject("compare response contains a non-object file record")
        additions, deletions = validate_file(item)
        total_additions += additions
        total_deletions += deletions

    pr_additions = pr.get("additions")
    pr_deletions = pr.get("deletions")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (pr_additions, pr_deletions)
    ):
        reject("PR change totals are malformed")
    if pr_additions != total_additions or pr_deletions != total_deletions:
        reject("file change totals are inconsistent with the PR metadata")


def validate(
    pr: dict,
    compare: dict,
    event_number: str,
    expected_base_oid: str,
    expected_head_oid: str,
    expected_head_ref: str,
    expected_repository: str = EXPECTED_REPOSITORY,
) -> dict:
    result = validate_identity(
        pr,
        event_number,
        expected_base_oid,
        expected_head_oid,
        expected_head_ref,
        expected_repository,
    )
    if result["eligible"]:
        validate_compare(compare, pr, expected_base_oid, expected_head_oid)
    return result


def write_outputs(result: dict, event_number: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        reject("GITHUB_OUTPUT is unavailable")
    outputs = {
        "eligible": "true" if result["eligible"] else "false",
        "pr_number": event_number,
        "base_oid": result["base_oid"],
        "head_oid": result["head_oid"],
        "head_ref": result["head_ref"],
    }
    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write("%s=%s\n" % (key, value))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        reject("usage: validate_dependabot_actions.py PR_JSON COMPARE_JSON")
    event_number = os.environ.get("EVENT_PR_NUMBER", "")
    expected_base_oid = os.environ.get("EXPECTED_BASE_OID", "")
    expected_head_oid = os.environ.get("EXPECTED_HEAD_OID", "")
    expected_head_ref = os.environ.get("EXPECTED_HEAD_REF", "")
    pr = load_json(argv[0])
    compare = load_json(argv[1])
    result = validate(
        pr,
        compare,
        event_number,
        expected_base_oid,
        expected_head_oid,
        expected_head_ref,
    )
    write_outputs(result, event_number)
    if not result["eligible"]:
        print("draft Dependabot PR; no auto-merge mutation")
    else:
        print("validated exact Dependabot Action diff at %s" % expected_head_oid)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
