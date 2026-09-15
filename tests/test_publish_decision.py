"""Publish decision behavior: one production interface for both event adapters."""

import importlib.util
import json
import os
import tempfile
import types
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(REPO_ROOT, "tools", "publish_decision.py")


def load_decision():
    import sys

    spec = importlib.util.spec_from_file_location("publish_decision", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["publish_decision"] = module
    spec.loader.exec_module(module)
    return module


DECISION = load_decision()
DecideInput = DECISION.DecideInput
PublishDecisionError = DECISION.PublishDecisionError
decide = DECISION.decide

SHA = "e872793eb9471205c1f37e91891fedd0b827e3c1"
OTHER_SHA = "a" * 40


def pins(version="0.48.0"):
    return f"version: {version}\ncommitSha: {'b' * 40}\n"


def auto_input(version="0.48.0", tags=(), sha=SHA):
    return DecideInput(
        event_name="workflow_run",
        trigger_conclusion="success",
        trigger_event="workflow_run",
        trigger_branch="main",
        trigger_sha=sha,
        pins_text=pins(version),
        raw_tags=tuple(tags),
    )


def manual_input(version="0.48.0", tags=(), sha=SHA, reason="packaging fix"):
    run = {"conclusion": "success", "head_sha": sha, "event": "push"}
    xrun = {"conclusion": "success", "head_sha": sha, "event": "workflow_run"}
    return DecideInput(
        event_name="workflow_dispatch",
        dispatch_sha=sha,
        dispatch_ref="refs/heads/main",
        reason=reason,
        pins_text=pins(version),
        raw_tags=tuple(tags),
        validate_runs=(run,),
        x3_runs=(xrun,),
        sha_exists=True,
        is_ancestor=True,
    )


class EventModeTests(unittest.TestCase):
    def test_unknown_event_fails_closed(self):
        with self.assertRaises(PublishDecisionError):
            decide(DecideInput(event_name="push", pins_text=pins(), raw_tags=()))

    def test_non_success_chain_noops_without_sha(self):
        request = DecideInput(
            event_name="workflow_run",
            trigger_conclusion="success",
            trigger_event="workflow_dispatch",
            trigger_branch="main",
            trigger_sha=SHA,
            pins_text=pins(),
            raw_tags=(),
        )
        decision = decide(request)
        self.assertFalse(decision.proceed)
        self.assertEqual(decision.mode, "auto")
        self.assertFalse(decision.is_new)
        self.assertEqual(decision.sha, "")
        self.assertEqual(decision.version, "")

    def test_malformed_sha_fails_closed_both_modes(self):
        for bad in ("", "not-a-sha", "A" * 40, SHA[:-1], SHA + "0"):
            with self.subTest(bad=bad):
                with self.assertRaises(PublishDecisionError):
                    decide(auto_input(sha=bad))
                with self.assertRaises(PublishDecisionError):
                    decide(manual_input(sha=bad))


class VersionProvenanceTests(unittest.TestCase):
    def test_malformed_pins_fail_closed(self):
        for bad in ("", "version: bogus\n", "version: 1.2\n", "version: 1..2\n", "other: 1\n"):
            with self.subTest(bad=bad):
                with self.assertRaises(PublishDecisionError):
                    decide(DecideInput(
                        event_name="workflow_run",
                        trigger_conclusion="success",
                        trigger_event="workflow_run",
                        trigger_branch="main",
                        trigger_sha=SHA,
                        pins_text=bad,
                        raw_tags=(),
                    ))

    def test_genuinely_empty_provenance_bootstraps(self):
        decision = decide(auto_input(version="0.47.0", tags=[]))
        self.assertTrue(decision.proceed)
        self.assertTrue(decision.is_new)

    def test_malformed_only_provenance_fails_closed(self):
        with self.assertRaises(PublishDecisionError):
            decide(auto_input(version="0.48.0", tags=["v1.2"]))
        with self.assertRaises(PublishDecisionError):
            decide(auto_input(version="0.48.0", tags=["flatpak/0.47.0-rX"]))

    def test_deployed_markers_excluded(self):
        tags = ["flatpak/0.46.0-r1", "flatpak/deployed-0.46.0-r1",
                "flatpak/0.47.0-r10", "flatpak/deployed-0.47.0-r10"]
        decision = decide(auto_input(version="0.48.0", tags=tags))
        self.assertTrue(decision.proceed)
        self.assertTrue(decision.is_new)
        noop = decide(auto_input(version="0.47.0", tags=tags))
        self.assertFalse(noop.proceed)
        self.assertEqual(noop.sha, SHA)

    def test_new_same_older_semantics(self):
        self.assertTrue(decide(auto_input("0.48.0", ["v0.47.0"])).proceed)
        self.assertFalse(decide(auto_input("0.47.0", ["v0.47.0"])).proceed)
        self.assertFalse(decide(auto_input("0.46.0", ["v0.47.0"])).proceed)

    def test_foreign_tags_ignored(self):
        decision = decide(auto_input("0.47.0", ["nightly", "", None]))
        self.assertTrue(decision.proceed)


class ManualIntentTests(unittest.TestCase):
    def test_non_main_ref_rejected(self):
        request = manual_input()
        bad = DecideInput(**{**request.__dict__, "dispatch_ref": "refs/heads/fix/x"})
        with self.assertRaises(PublishDecisionError):
            decide(bad)

    def test_empty_reason_rejected_but_quoted_newline_accepted(self):
        with self.assertRaises(PublishDecisionError):
            decide(manual_input(reason=""))
        with self.assertRaises(PublishDecisionError):
            decide(manual_input(reason="   \n  "))
        tricky = 'fix "quoted" packaging\nsecond line with $HOME and `ticks`'
        decision = decide(manual_input(reason=tricky))
        self.assertTrue(decision.proceed)
        self.assertEqual(decision.mode, "manual")

    def test_ancestry_and_existence_fail_closed(self):
        base = manual_input()
        for field in ("sha_exists", "is_ancestor"):
            kwargs = dict(base.__dict__)
            kwargs[field] = False
            with self.subTest(field=field):
                with self.assertRaises(PublishDecisionError):
                    decide(DecideInput(**kwargs))

    def test_exact_proof_required(self):
        base = manual_input()
        kwargs = dict(base.__dict__)
        kwargs["validate_runs"] = ({"conclusion": "failure", "head_sha": SHA, "event": "push"},)
        with self.assertRaises(PublishDecisionError):
            decide(DecideInput(**kwargs))
        kwargs = dict(base.__dict__)
        kwargs["x3_runs"] = ({"conclusion": "success", "head_sha": SHA, "event": "push"},)
        with self.assertRaises(PublishDecisionError):
            decide(DecideInput(**kwargs))
        kwargs = dict(base.__dict__)
        kwargs["validate_runs"] = ({"conclusion": "success", "head_sha": OTHER_SHA, "event": "push"},)
        with self.assertRaises(PublishDecisionError):
            decide(DecideInput(**kwargs))

    def test_manual_older_version_fails_closed(self):
        with self.assertRaises(PublishDecisionError):
            decide(manual_input(version="0.46.0", tags=["v0.47.0"]))

    def test_manual_same_version_proceeds_not_new(self):
        decision = decide(manual_input(version="0.47.0", tags=["v0.47.0"]))
        self.assertTrue(decision.proceed)
        self.assertEqual(decision.mode, "manual")
        self.assertFalse(decision.is_new)
        self.assertEqual(decision.sha, SHA)
        self.assertEqual(decision.version, "0.47.0")

    def test_manual_newer_version_proceeds_new(self):
        decision = decide(manual_input(version="0.48.0", tags=["v0.47.0"]))
        self.assertTrue(decision.proceed)
        self.assertEqual(decision.mode, "manual")
        self.assertTrue(decision.is_new)
        self.assertEqual(decision.sha, SHA)
        self.assertEqual(decision.version, "0.48.0")

    def test_bounded_outputs_only(self):
        decision = decide(manual_input())
        self.assertEqual(set(decision.__dict__), {"proceed", "sha", "version", "mode", "is_new"})


def _ok(stdout=""):
    return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def _fail(code=1, stderr="boom"):
    return types.SimpleNamespace(returncode=code, stdout="", stderr=stderr)


def _read_outputs(path):
    values = {}
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle.read().splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def _run_main(env, stub):
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        outputs_path = handle.name
    try:
        full_env = {
            "EVENT_NAME": "",
            "TRIGGER_CONCLUSION": "",
            "TRIGGER_EVENT": "",
            "TRIGGER_BRANCH": "",
            "TRIGGER_SHA": "",
            "DISPATCH_SHA": "",
            "DISPATCH_REF": "",
            "INPUT_REASON": "",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": outputs_path,
        }
        full_env.update(env)
        with mock.patch.dict(os.environ, full_env, clear=False):
            with mock.patch.object(DECISION, "_run", side_effect=stub):
                code = DECISION.main([])
        return code, _read_outputs(outputs_path)
    finally:
        os.unlink(outputs_path)


def _auto_stub(pins_version="0.48.0", tags="v0.47.0\n", calls=None):
    def stub(argv, **kwargs):
        if calls is not None:
            calls.append(list(argv))
        if argv[:2] == ["git", "show"]:
            return _ok(f"version: {pins_version}\n")
        if argv == ["git", "fetch", "--tags", "origin"]:
            return _ok()
        if argv == ["git", "tag", "--list"]:
            return _ok(tags)
        raise AssertionError(f"unexpected call {argv!r}")
    return stub


def _manual_stub(pins_version="0.48.0", tags="v0.47.0\n",
                 validate_runs=None, x3_runs=None, calls=None,
                 fetch_main_code=0, fetch_tags_code=0, merge_code=0):
    validate_runs = [{"conclusion": "success", "head_sha": SHA, "event": "push"}] \
        if validate_runs is None else validate_runs
    x3_runs = [{"conclusion": "success", "head_sha": SHA, "event": "workflow_run"}] \
        if x3_runs is None else x3_runs

    def stub(argv, **kwargs):
        if calls is not None:
            calls.append(list(argv))
        if argv[:2] == ["git", "show"]:
            return _ok(f"version: {pins_version}\n")
        if argv[:2] == ["git", "cat-file"]:
            return _ok()
        if argv == ["git", "fetch", "origin", "main"]:
            return _ok() if fetch_main_code == 0 else _fail(fetch_main_code)
        if argv[:2] == ["git", "merge-base"]:
            if merge_code == 0:
                return _ok()
            return _fail(merge_code)
        if argv[:2] == ["gh", "api"]:
            endpoint = argv[2]
            if "validate.yml" in endpoint:
                return _ok(json.dumps({"workflow_runs": validate_runs}))
            if "x3.yml" in endpoint:
                return _ok(json.dumps({"workflow_runs": x3_runs}))
            raise AssertionError(f"unexpected endpoint {endpoint!r}")
        if argv == ["git", "fetch", "--tags", "origin"]:
            return _ok() if fetch_tags_code == 0 else _fail(fetch_tags_code)
        if argv == ["git", "tag", "--list"]:
            return _ok(tags)
        raise AssertionError(f"unexpected call {argv!r}")
    return stub


class MainAdapterTests(unittest.TestCase):
    """Prove the production main() adapter, not just pure decide()."""

    def test_auto_success_writes_exact_bounded_outputs(self):
        calls = []
        code, outputs = _run_main(
            {
                "EVENT_NAME": "workflow_run",
                "TRIGGER_CONCLUSION": "success",
                "TRIGGER_EVENT": "workflow_run",
                "TRIGGER_BRANCH": "main",
                "TRIGGER_SHA": SHA,
            },
            _auto_stub(pins_version="0.48.0", tags="v0.47.0\n", calls=calls),
        )
        self.assertEqual(code, 0)
        self.assertEqual(outputs, {
            "proceed": "true",
            "sha": SHA,
            "version": "0.48.0",
            "mode": "auto",
            "is_new": "true",
        })
        self.assertTrue(any(argv[:2] == ["git", "show"] for argv in calls))

    def test_auto_non_success_noops_without_sha_or_git_work(self):
        for trigger_sha in ("", "bogus"):
            with self.subTest(trigger_sha=trigger_sha):
                calls = []
                def stub(argv, **kwargs):
                    calls.append(list(argv))
                    raise AssertionError(f"git/gh must not run for no-op: {argv!r}")
                code, outputs = _run_main(
                    {
                        "EVENT_NAME": "workflow_run",
                        "TRIGGER_CONCLUSION": "failure",
                        "TRIGGER_EVENT": "workflow_run",
                        "TRIGGER_BRANCH": "main",
                        "TRIGGER_SHA": trigger_sha,
                    },
                    stub,
                )
                self.assertEqual(code, 0)
                self.assertEqual(outputs, {"proceed": "false", "mode": "auto", "is_new": "false"})
                self.assertEqual(calls, [])

    def test_manual_quoted_newline_reason_is_opaque_and_proven(self):
        tricky = 'fix "quoted" packaging\nsecond line with $HOME and `ticks`'
        code, outputs = _run_main(
            {
                "EVENT_NAME": "workflow_dispatch",
                "DISPATCH_SHA": SHA,
                "DISPATCH_REF": "refs/heads/main",
                "INPUT_REASON": tricky,
            },
            _manual_stub(pins_version="0.48.0", tags="v0.47.0\n"),
        )
        self.assertEqual(code, 0)
        self.assertEqual(outputs, {
            "proceed": "true",
            "sha": SHA,
            "version": "0.48.0",
            "mode": "manual",
            "is_new": "true",
        })

    def test_fetch_failures_fail_closed_without_proceed_true(self):
        code, outputs = _run_main(
            {
                "EVENT_NAME": "workflow_dispatch",
                "DISPATCH_SHA": SHA,
                "DISPATCH_REF": "refs/heads/main",
                "INPUT_REASON": "republish",
            },
            _manual_stub(fetch_main_code=1),
        )
        self.assertEqual(code, 1)
        self.assertNotEqual(outputs.get("proceed"), "true")
        code, outputs = _run_main(
            {
                "EVENT_NAME": "workflow_run",
                "TRIGGER_CONCLUSION": "success",
                "TRIGGER_EVENT": "workflow_run",
                "TRIGGER_BRANCH": "main",
                "TRIGGER_SHA": SHA,
            },
            _auto_stub(),
        )
        # Sanity: the passing auto above proves the next failure is the fetch.
        self.assertEqual(code, 0)
        def tag_fetch_fail(argv, **kwargs):
            if argv == ["git", "fetch", "--tags", "origin"]:
                return _fail(1)
            return _auto_stub()(argv, **kwargs)
        code, outputs = _run_main(
            {
                "EVENT_NAME": "workflow_run",
                "TRIGGER_CONCLUSION": "success",
                "TRIGGER_EVENT": "workflow_run",
                "TRIGGER_BRANCH": "main",
                "TRIGGER_SHA": SHA,
            },
            tag_fetch_fail,
        )
        self.assertEqual(code, 1)
        self.assertNotEqual(outputs.get("proceed"), "true")

    def test_malformed_gh_responses_fail_closed(self):
        def bad_json(argv, **kwargs):
            if argv[:2] == ["git", "show"]:
                return _ok("version: 0.48.0\n")
            if argv[:2] == ["git", "cat-file"]:
                return _ok()
            if argv == ["git", "fetch", "origin", "main"]:
                return _ok()
            if argv[:2] == ["git", "merge-base"]:
                return _ok()
            if argv[:2] == ["gh", "api"]:
                return _ok("not-json{")
            raise AssertionError(argv)
        code, outputs = _run_main(
            {
                "EVENT_NAME": "workflow_dispatch",
                "DISPATCH_SHA": SHA,
                "DISPATCH_REF": "refs/heads/main",
                "INPUT_REASON": "republish",
            },
            bad_json,
        )
        self.assertEqual(code, 1)
        self.assertNotEqual(outputs.get("proceed"), "true")

        def bad_shape(argv, **kwargs):
            if argv[:2] == ["git", "show"]:
                return _ok("version: 0.48.0\n")
            if argv[:2] == ["git", "cat-file"]:
                return _ok()
            if argv == ["git", "fetch", "origin", "main"]:
                return _ok()
            if argv[:2] == ["git", "merge-base"]:
                return _ok()
            if argv[:2] == ["gh", "api"]:
                return _ok(json.dumps({"workflow_runs": "nope"}))
            raise AssertionError(argv)
        code, outputs = _run_main(
            {
                "EVENT_NAME": "workflow_dispatch",
                "DISPATCH_SHA": SHA,
                "DISPATCH_REF": "refs/heads/main",
                "INPUT_REASON": "republish",
            },
            bad_shape,
        )
        self.assertEqual(code, 1)
        self.assertNotEqual(outputs.get("proceed"), "true")

    def test_proof_event_asymmetry_and_identity(self):
        good_validate = {"conclusion": "success", "head_sha": SHA, "event": "push"}
        good_x3 = {"conclusion": "success", "head_sha": SHA, "event": "workflow_run"}
        cases = [
            # validate family
            ([{"conclusion": "success", "head_sha": SHA, "event": "workflow_run"}],
             [good_x3], "validate must reject workflow_run"),
            ([{"conclusion": "failure", "head_sha": SHA, "event": "push"}],
             [good_x3], "validate must reject failure"),
            ([{"conclusion": "success", "head_sha": OTHER_SHA, "event": "push"}],
             [good_x3], "validate must reject wrong SHA"),
            ([], [good_x3], "validate must reject empty"),
            # x3 family
            ([good_validate],
             [{"conclusion": "success", "head_sha": SHA, "event": "push"}],
             "x3 must reject push"),
            ([good_validate],
             [{"conclusion": "failure", "head_sha": SHA, "event": "workflow_run"}],
             "x3 must reject failure"),
            ([good_validate],
             [{"conclusion": "success", "head_sha": OTHER_SHA, "event": "workflow_run"}],
             "x3 must reject wrong SHA"),
            ([good_validate], [], "x3 must reject empty"),
        ]
        for validate_runs, x3_runs, message in cases:
            with self.subTest(message=message):
                code, outputs = _run_main(
                    {
                        "EVENT_NAME": "workflow_dispatch",
                        "DISPATCH_SHA": SHA,
                        "DISPATCH_REF": "refs/heads/main",
                        "INPUT_REASON": "republish",
                    },
                    _manual_stub(validate_runs=validate_runs, x3_runs=x3_runs),
                )
                self.assertEqual(code, 1, message)
                self.assertNotEqual(outputs.get("proceed"), "true", message)


if __name__ == "__main__":
    unittest.main()
