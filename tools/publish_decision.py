#!/usr/bin/env python3
"""Publish decision policy for the release gate.

Single production seam for the decide job: both the automatic
workflow_run path and the manual workflow_dispatch path cross
``decide``. Tests cross the same interface with stub data; the
workflow calls this module through its CLI adapter, which reads
explicit GitHub env bindings and trusted git/gh bytes.

Bounded outputs only: proceed, sha, version, mode, is_new.
Every failure raises PublishDecisionError and publishes nothing.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
STRICT_PUBLIC_RE = re.compile(r"^v(\d+\.\d+\.\d+)$")
STRICT_INTERNAL_RE = re.compile(r"^flatpak/(\d+\.\d+\.\d+)-r\d+$")
VALIDATE_EVENTS = frozenset({"push", "workflow_dispatch"})
X3_EVENTS = frozenset({"workflow_run", "workflow_dispatch"})


class PublishDecisionError(Exception):
    """Fail-closed verdict for any decision step."""


@dataclass(frozen=True)
class Decision:
    proceed: bool
    sha: str
    version: str
    mode: str
    is_new: bool


@dataclass(frozen=True)
class DecideInput:
    event_name: str = ""
    trigger_conclusion: str = ""
    trigger_event: str = ""
    trigger_branch: str = ""
    trigger_sha: str = ""
    dispatch_sha: str = ""
    dispatch_ref: str = ""
    reason: str = ""
    pins_text: str = ""
    raw_tags: tuple = field(default_factory=tuple)
    validate_runs: tuple = field(default_factory=tuple)
    x3_runs: tuple = field(default_factory=tuple)
    sha_exists: bool = False
    is_ancestor: bool = False


def validate_sha(value: object) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise PublishDecisionError("SHA must be an exact 40-char lowercase hex")
    return value


def parse_pinned_version(pins_text: object) -> str:
    if not isinstance(pins_text, str) or not pins_text:
        raise PublishDecisionError("pinned version is malformed")
    found: list[str] = []
    for line in pins_text.splitlines():
        if not line.startswith("version:"):
            continue
        parts = line.split()
        if len(parts) != 2 or parts[0] != "version:":
            raise PublishDecisionError("pinned version is malformed")
        found.append(parts[1])
    if len(found) != 1:
        raise PublishDecisionError("pinned version is malformed")
    version = found[0]
    if not VERSION_RE.fullmatch(version):
        raise PublishDecisionError("pinned version is not X.Y.Z")
    return version


def _is_relevant_tag(tag: str) -> bool:
    return fnmatch.fnmatchcase(tag, "v[0-9]*") or fnmatch.fnmatchcase(
        tag, "flatpak/[0-9]*-r*"
    )


def collect_published_versions(raw_tags) -> list[str]:
    """Strict provenance: public vX.Y.Z and internal flatpak/X.Y.Z-rN only.

    Deployed markers (flatpak/deployed-*) and foreign tags are ignored
    via the relevant globs. A relevant tag that matches those globs
    but fails strict semver fails closed.
    """
    found: set[str] = set()
    for entry in raw_tags or []:
        text = str(entry or "").strip()
        if not text:
            continue
        if not _is_relevant_tag(text):
            continue
        public = STRICT_PUBLIC_RE.fullmatch(text)
        if public:
            found.add(public.group(1))
            continue
        internal = STRICT_INTERNAL_RE.fullmatch(text)
        if internal:
            found.add(internal.group(1))
            continue
        raise PublishDecisionError(f"malformed publication tag {text!r}")
    return sorted(found, key=lambda v: tuple(int(p) for p in v.split(".")))


def is_new_version(current: str, raw_tags) -> bool:
    if not isinstance(current, str) or not VERSION_RE.fullmatch(current):
        raise PublishDecisionError("pinned version is not X.Y.Z")
    published = collect_published_versions(raw_tags)
    if current in published:
        return False
    if not published:
        return True
    key = tuple(int(p) for p in current.split("."))
    highest = max(tuple(int(p) for p in v.split(".")) for v in published)
    return key > highest


def _runs_prove_sha(runs, sha: str, allowed: frozenset) -> bool:
    for run in runs or []:
        if not isinstance(run, dict):
            continue
        if run.get("conclusion") != "success":
            continue
        if run.get("head_sha") != sha:
            continue
        if run.get("event") not in allowed:
            continue
        return True
    return False


def decide(request: DecideInput) -> Decision:
    if request.event_name == "workflow_run":
        mode = "auto"
        if (
            request.trigger_conclusion != "success"
            or request.trigger_event != "workflow_run"
            or request.trigger_branch != "main"
        ):
            return Decision(False, "", "", "auto", False)
        sha = validate_sha(request.trigger_sha)
    elif request.event_name == "workflow_dispatch":
        mode = "manual"
        if request.dispatch_ref != "refs/heads/main":
            raise PublishDecisionError("manual publish must dispatch from refs/heads/main")
        sha = validate_sha(request.dispatch_sha)
        if not isinstance(request.reason, str) or not request.reason.strip():
            raise PublishDecisionError("manual publish requires a reason")
        if not request.sha_exists:
            raise PublishDecisionError("dispatched SHA does not exist")
        if not request.is_ancestor:
            raise PublishDecisionError("dispatched SHA is not on main history")
        if not _runs_prove_sha(request.validate_runs, sha, VALIDATE_EVENTS):
            raise PublishDecisionError(f"no successful validate run for {sha}")
        if not _runs_prove_sha(request.x3_runs, sha, X3_EVENTS):
            raise PublishDecisionError(f"no successful dual-arch X3 run for {sha}")
    else:
        raise PublishDecisionError(f"unexpected event {request.event_name!r}")
    version = parse_pinned_version(request.pins_text)
    is_new = is_new_version(version, request.raw_tags)
    if mode == "auto" and not is_new:
        return Decision(False, sha, version, "auto", False)
    return Decision(True, sha, version, mode, is_new)


def _run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs)


def _require_git_ok(proc: subprocess.CompletedProcess, what: str) -> str:
    if proc.returncode != 0:
        raise PublishDecisionError(f"{what} failed: {(proc.stderr or '').strip()}")
    return proc.stdout or ""


def _fetch_or_fail(argv: list[str], what: str) -> None:
    proc = _run(argv)
    if proc.returncode != 0:
        raise PublishDecisionError(f"{what} failed; refusing on stale refs")


def _fetch_runs(workflow: str, sha: str, repo: str) -> list:
    if not repo or "/" not in repo:
        raise PublishDecisionError("GITHUB_REPOSITORY is malformed")
    endpoint = f"repos/{repo}/actions/workflows/{workflow}/runs?head_sha={sha}&per_page=20"
    proc = _run(["gh", "api", endpoint])
    if proc.returncode != 0:
        raise PublishDecisionError(f"failed to query {workflow} runs for {sha}")
    try:
        payload = json.loads(proc.stdout or "")
    except ValueError as exc:
        raise PublishDecisionError(f"malformed {workflow} runs response") from exc
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        raise PublishDecisionError(f"malformed {workflow} runs response")
    return runs


def _write_outputs(decision: Decision) -> None:
    path = os.environ.get("GITHUB_OUTPUT", "")
    if not path:
        raise PublishDecisionError("GITHUB_OUTPUT is unavailable")
    lines = [f"proceed={'true' if decision.proceed else 'false'}"]
    if decision.sha:
        lines.append(f"sha={decision.sha}")
    if decision.version:
        lines.append(f"version={decision.version}")
    lines.append(f"mode={decision.mode}")
    lines.append(f"is_new={'true' if decision.is_new else 'false'}")
    with open(path, "a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print("usage: publish_decision.py (reads GitHub env, writes GITHUB_OUTPUT)")
        return 0
    try:
        event = os.environ.get("EVENT_NAME", "")
        trigger_sha = os.environ.get("TRIGGER_SHA", "")
        dispatch_sha = os.environ.get("DISPATCH_SHA", "")
        if event == "workflow_run":
            sha = trigger_sha
        elif event == "workflow_dispatch":
            validate_sha(dispatch_sha)
            sha = dispatch_sha
        else:
            raise PublishDecisionError(f"unexpected event {event!r}")
        if event == "workflow_run" and (
            os.environ.get("TRIGGER_CONCLUSION", "") != "success"
            or os.environ.get("TRIGGER_EVENT", "") != "workflow_run"
            or os.environ.get("TRIGGER_BRANCH", "") != "main"
        ):
            _write_outputs(Decision(False, "", "", "auto", False))
            print("not a successful chain X3 run on main; skipping automatic publication (no-op success)")
            return 0
        if event == "workflow_run":
            validate_sha(sha)
        show = _run(["git", "show", f"{sha}:data/pins.yml"])
        pins_text = _require_git_ok(show, "pinned version lookup")
        raw_tags: list[str] = []
        validate_runs: list = []
        x3_runs: list = []
        sha_exists = True
        is_ancestor = True
        if event == "workflow_dispatch":
            exists = _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"])
            sha_exists = exists.returncode == 0
            _fetch_or_fail(["git", "fetch", "origin", "main"], "main refresh")
            ancestor = _run(["git", "merge-base", "--is-ancestor", sha, "origin/main"])
            if ancestor.returncode == 0:
                is_ancestor = True
            elif ancestor.returncode == 1:
                is_ancestor = False
            else:
                raise PublishDecisionError("ancestry check failed; refusing on stale refs")
            repo = os.environ.get("GITHUB_REPOSITORY", "")
            validate_runs = _fetch_runs("validate.yml", sha, repo)
            x3_runs = _fetch_runs("x3.yml", sha, repo)
        _fetch_or_fail(["git", "fetch", "--tags", "origin"], "tag refresh")
        tags_out = _require_git_ok(_run(["git", "tag", "--list"]), "tag listing")
        raw_tags = tags_out.split()
        request = DecideInput(
            event_name=event,
            trigger_conclusion=os.environ.get("TRIGGER_CONCLUSION", ""),
            trigger_event=os.environ.get("TRIGGER_EVENT", ""),
            trigger_branch=os.environ.get("TRIGGER_BRANCH", ""),
            trigger_sha=trigger_sha,
            dispatch_sha=dispatch_sha,
            dispatch_ref=os.environ.get("DISPATCH_REF", ""),
            reason=os.environ.get("INPUT_REASON", ""),
            pins_text=pins_text,
            raw_tags=tuple(raw_tags),
            validate_runs=tuple(validate_runs),
            x3_runs=tuple(x3_runs),
            sha_exists=sha_exists,
            is_ancestor=is_ancestor,
        )
        decision = decide(request)
        _write_outputs(decision)
        if not decision.proceed:
            print(f"version {decision.version or 'unknown'} is not new; skipping automatic publication (no-op success)")
        else:
            print(f"publish decided: mode={decision.mode} sha={decision.sha} version={decision.version} is_new={str(decision.is_new).lower()}")
        return 0
    except PublishDecisionError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
