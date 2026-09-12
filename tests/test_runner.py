"""Workspace runner checks: fail-closed parsing plus payload/companion gates.

Phase 1 wires the runner self-checks. Phase 2 adds payload and companion
rejection checks. Phase 3 adds the atomic-release gate checks.
"""

import importlib.util
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_RUNNER_PATH = os.path.join(REPO_ROOT, "tools", "test.py")


def load_workspace_runner():
    """Import tools/test.py without adding tools/ to sys.path."""
    spec = importlib.util.spec_from_file_location(
        "workspace_test_runner", TEST_RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkspaceRunnerModuleTests(unittest.TestCase):
    def test_runner_module_exists(self):
        self.assertTrue(
            os.path.isfile(TEST_RUNNER_PATH),
            "tools/test.py must exist as the single workspace entry point",
        )

    def test_runner_module_exposes_fail_closed_helpers(self):
        runner = load_workspace_runner()
        for name in (
            "parse_unittest_summary",
            "python_layer_passes",
            "ctest_output_has_no_tests",
            "ctest_layer_passes",
            "run_python_layer",
            "run_ctest_layer",
            "main",
        ):
            self.assertTrue(callable(getattr(runner, name, None)), name)

    def test_tests_directory_exists(self):
        self.assertTrue(os.path.isdir(os.path.join(REPO_ROOT, "tests")))


class FailClosedParsingTests(unittest.TestCase):
    """The gate must reject empty or undeterminable layers, never skip them."""

    def test_zero_python_tests_fail_closed(self):
        runner = load_workspace_runner()
        self.assertFalse(runner.python_layer_passes(0, "Ran 0 tests in 0.000s\n\nOK\n"))

    def test_unparseable_python_output_fails_closed(self):
        runner = load_workspace_runner()
        self.assertFalse(runner.python_layer_passes(0, ""))
        self.assertFalse(runner.python_layer_passes(0, "some unrelated output"))

    def test_failing_python_suite_fails_closed(self):
        runner = load_workspace_runner()
        self.assertFalse(
            runner.python_layer_passes(1, "Ran 4 tests in 0.001s\n\nFAILED (failures=1)\n")
        )

    def test_passing_python_suite_requires_ok_and_count(self):
        runner = load_workspace_runner()
        self.assertTrue(
            runner.python_layer_passes(0, "Ran 4 tests in 0.001s\n\nOK\n")
        )
        self.assertFalse(runner.python_layer_passes(0, "Ran 4 tests in 0.001s\n"))

    def test_ctest_no_tests_found_fails_closed(self):
        runner = load_workspace_runner()
        self.assertTrue(runner.ctest_output_has_no_tests("No tests were found!!!\n"))
        self.assertFalse(
            runner.ctest_layer_passes(True, True, 0, "No tests were found!!!\n")
        )

    def test_ctest_layer_requires_every_step(self):
        runner = load_workspace_runner()
        good = "100% tests passed, 0 tests failed out of 1"
        self.assertTrue(runner.ctest_layer_passes(True, True, 0, good))
        self.assertFalse(runner.ctest_layer_passes(False, False, 1, ""))
        self.assertFalse(runner.ctest_layer_passes(True, False, 1, ""))
        self.assertFalse(runner.ctest_layer_passes(True, True, 1, good))


MANIFEST_PATH = os.path.join(
    REPO_ROOT, "io.github.viniciosrab.GrokBot.yml"
)
DESKTOP_PATH = os.path.join(
    REPO_ROOT, "data", "io.github.viniciosrab.GrokBot.desktop"
)
METAINFO_PATH = os.path.join(
    REPO_ROOT, "data", "io.github.viniciosrab.GrokBot.metainfo.xml"
)
COMPANION_SRC = os.path.join(REPO_ROOT, "companion", "src", "main.cpp")
COMPANION_CMAKE = os.path.join(REPO_ROOT, "companion", "CMakeLists.txt")

WATCHER_NAME = "org.kde.StatusNotifierWatcher"
VENDOR_ICON_512 = "usr/share/icons/hicolor/512x512/apps/grok-bot.png"
VENDOR_HICOLOR_TREE = "usr/share/icons/hicolor"

# Closed finish-args set from the design contract. No more, no less.
CLOSED_FINISH_ARGS = {
    "--share=ipc",
    "--socket=wayland",
    "--socket=fallback-x11",
    "--socket=pulseaudio",
    "--share=network",
    "--device=dri",
    "--talk-name=org.kde.StatusNotifierWatcher",
    "--env=SAND_DISABLE_UPDATES=1",
    "--env=ELECTRON_TRASH=gio",
    "--env=XCURSOR_PATH=/run/host/user-share/icons:/run/host/share/icons",
}


def read_repo_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def manifest_finish_args(text):
    """Collect `--...` entries from the manifest finish-args block."""
    args = set()
    in_block = False
    for line in text.splitlines():
        if line.strip() == "finish-args:":
            in_block = True
            continue
        if in_block:
            stripped = line.strip()
            if stripped.startswith("- --"):
                args.add(stripped[2:].strip())
            elif stripped and not line.startswith((" ", "\t")):
                break
    return args


def check_status_notifier_watcher(manifest_text, companion_src):
    """Watcher talk-name in finish-args and a watcher gate in the companion."""
    if "--talk-name=" + WATCHER_NAME not in manifest_text:
        return False
    if WATCHER_NAME not in companion_src:
        return False
    return "return 1" in companion_src


def check_vendor_icon(manifest_text):
    """Vendor 512 icon plus full hicolor tree; never a redesigned icon."""
    if "resources/icon.png" in manifest_text:
        return False
    return VENDOR_ICON_512 in manifest_text and VENDOR_HICOLOR_TREE in manifest_text


def check_electron_exec(manifest_text, desktop_text):
    """Electron Exec is derived from the unpacked artifact (missing rejects)
    and the desktop entry launches the companion with the vendor icon."""
    if "Exec" not in manifest_text or "exit 1" not in manifest_text:
        return False
    exec_lines = [
        line.strip()
        for line in desktop_text.splitlines()
        if line.strip().startswith("Exec=")
    ]
    if len(exec_lines) != 1 or "companion" not in exec_lines[0]:
        return False
    icon_lines = [
        line.strip()
        for line in desktop_text.splitlines()
        if line.strip().startswith("Icon=")
    ]
    return icon_lines == ["Icon=io.github.viniciosrab.GrokBot"]


def check_kde_electron_runtime(manifest_text, companion_src):
    """KDE 6.11 runtime, zypak as a module (never an Electron BaseApp base),
    companion command, and KF6 SNI lifecycle in the companion."""
    for required in ("org.kde.Platform", "org.kde.Sdk", "6.11", "zypak"):
        if required not in manifest_text:
            return False
    if "Electron2.BaseApp" in manifest_text:
        return False
    if "command: grok-bot-companion" not in manifest_text:
        return False
    for required in (
        "KStatusNotifierItem",
        "qApp->quit()",
        "org.kde.StatusNotifierItem-",
    ):
        if required not in companion_src:
            return False
    if "killpg" not in companion_src and "setsid" not in companion_src:
        return False
    return True


def payload_checks(manifest_text, desktop_text, companion_src):
    """Every payload/runtime requirement for one architecture."""
    return {
        "finish-args-closed": manifest_finish_args(manifest_text) == CLOSED_FINISH_ARGS,
        "watcher": check_status_notifier_watcher(manifest_text, companion_src),
        "vendor-icon": check_vendor_icon(manifest_text),
        "electron-exec": check_electron_exec(manifest_text, desktop_text),
        "kde-electron-runtime": check_kde_electron_runtime(manifest_text, companion_src),
    }


def validation_verdict(checks):
    """An architecture is accepted only when every check passes.

    Validation never changes OSTree content: rejection and acceptance both
    report ostree_changed=False. Publication is a separate gated step.
    """
    accepted = bool(checks) and all(checks.values())
    return accepted, False


class PayloadCheckHelperTests(unittest.TestCase):
    def test_closed_finish_args_detects_drift(self):
        self.assertEqual(
            manifest_finish_args("finish-args:\n  - --share=ipc\n  - --socket=wayland\n"),
            {"--share=ipc", "--socket=wayland"},
        )

    def test_single_failed_check_rejects_without_ostree_change(self):
        checks = {
            "finish-args-closed": True,
            "watcher": False,
            "vendor-icon": True,
            "electron-exec": True,
            "kde-electron-runtime": True,
        }
        accepted, ostree_changed = validation_verdict(checks)
        self.assertFalse(accepted)
        self.assertFalse(ostree_changed)

    def test_all_passing_checks_accept_without_ostree_change(self):
        checks = {name: True for name in (
            "finish-args-closed",
            "watcher",
            "vendor-icon",
            "electron-exec",
            "kde-electron-runtime",
        )}
        accepted, ostree_changed = validation_verdict(checks)
        self.assertTrue(accepted)
        self.assertFalse(ostree_changed)

    def test_redesigned_icon_path_rejects(self):
        self.assertFalse(
            check_vendor_icon("install resources/icon.png to /app/share/icons")
        )

    def test_base_app_base_rejects(self):
        self.assertFalse(
            check_kde_electron_runtime(
                "runtime: org.kde.Platform\nbase: org.electronjs.Electron2.BaseApp\n",
                "KStatusNotifierItem qApp->quit() org.kde.StatusNotifierItem- setsid",
            )
        )


class PayloadContentContractTests(unittest.TestCase):
    """RED until tasks 2.3 (companion) and 2.4 (manifest/desktop) land."""

    def test_payload_files_exist(self):
        for path in (MANIFEST_PATH, DESKTOP_PATH, METAINFO_PATH,
                     COMPANION_SRC, COMPANION_CMAKE):
            self.assertTrue(os.path.isfile(path), f"missing: {path}")

    def test_payload_checks_accept(self):
        manifest_text = read_repo_text(MANIFEST_PATH)
        desktop_text = read_repo_text(DESKTOP_PATH)
        companion_src = read_repo_text(COMPANION_SRC)
        checks = payload_checks(manifest_text, desktop_text, companion_src)
        self.assertEqual(
            {name: passed for name, passed in checks.items() if not passed},
            {},
            f"failing payload checks: {checks}",
        )
        accepted, ostree_changed = validation_verdict(checks)
        self.assertTrue(accepted)
        self.assertFalse(ostree_changed)

    def test_metainfo_marks_unofficial(self):
        text = read_repo_text(METAINFO_PATH).lower()
        self.assertIn("unofficial", text)
        self.assertIn("grok-bot", text)


VALIDATE_WORKFLOW_PATH = os.path.join(
    REPO_ROOT, ".github", "workflows", "validate.yml"
)
PUBLISH_WORKFLOW_PATH = os.path.join(
    REPO_ROOT, ".github", "workflows", "publish.yml"
)
PINS_PATH = os.path.join(REPO_ROOT, "data", "pins.yml")

REQUIRED_ARCHES = ("x86_64", "aarch64")
REQUIRED_PUBLISH_SECRETS = ("GPG_KEY",)


def atomic_publish_verdict(per_arch):
    """One Atomic Flatpak Release publishes only when every supported
    architecture validated. Anything else publishes nothing."""
    if set(per_arch or {}) != set(REQUIRED_ARCHES):
        return False
    return all(per_arch[arch] for arch in REQUIRED_ARCHES)


def publish_effects(verdict):
    """A failed gate publishes no release and changes no OSTree content."""
    if verdict:
        return True, True
    return False, False


def manifest_arch_sources(manifest_text):
    """Map arch -> (url, sha256) from the manifest per-arch file sources."""
    sources = {}
    current_arch = None
    url = sha256 = None
    for line in manifest_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("only-arches:"):
            current_arch = None
            for arch in REQUIRED_ARCHES:
                if arch in stripped:
                    current_arch = arch
            url = sha256 = None
        elif stripped.startswith("url:") and current_arch:
            url = stripped.split("url:", 1)[1].strip()
        elif stripped.startswith("sha256:") and current_arch:
            sha256 = stripped.split("sha256:", 1)[1].strip()
            sources[current_arch] = (url, sha256)
            current_arch = None
    return sources


class AtomicGateHelperTests(unittest.TestCase):
    def test_both_arches_required(self):
        self.assertTrue(
            atomic_publish_verdict({"x86_64": True, "aarch64": True})
        )
        self.assertFalse(
            atomic_publish_verdict({"x86_64": True, "aarch64": False})
        )
        self.assertFalse(
            atomic_publish_verdict({"x86_64": False, "aarch64": True})
        )
        self.assertFalse(atomic_publish_verdict({"x86_64": True}))
        self.assertFalse(atomic_publish_verdict({}))
        self.assertFalse(
            atomic_publish_verdict(
                {"x86_64": True, "aarch64": True, "riscv64": True}
            )
        )

    def test_failed_gate_publishes_nothing(self):
        release, ostree = publish_effects(False)
        self.assertFalse(release)
        self.assertFalse(ostree)

    def test_source_payload_runtime_failure_blocks_arch(self):
        checks = {
            "finish-args-closed": True,
            "watcher": True,
            "vendor-icon": False,
            "electron-exec": True,
            "kde-electron-runtime": True,
        }
        accepted, ostree_changed = validation_verdict(checks)
        verdict = atomic_publish_verdict(
            {"x86_64": accepted, "aarch64": True}
        )
        self.assertFalse(accepted)
        self.assertFalse(verdict)
        release, ostree = publish_effects(verdict)
        self.assertFalse(release)
        self.assertFalse(ostree)
        self.assertFalse(ostree_changed)


class AtomicContentContractTests(unittest.TestCase):
    """RED until tasks 3.2 (validate.yml) and 3.3 (publish.yml) land."""

    def test_validate_covers_both_arches(self):
        self.assertTrue(os.path.isfile(VALIDATE_WORKFLOW_PATH))
        text = read_repo_text(VALIDATE_WORKFLOW_PATH)
        self.assertIn("ubuntu-24.04-arm", text)
        self.assertIn("ubuntu-24.04", text)
        self.assertIn("fail-fast: false", text)
        self.assertNotIn("continue-on-error: true", text)

    def test_validate_runs_workspace_gate_and_payload_proof(self):
        text = read_repo_text(VALIDATE_WORKFLOW_PATH)
        self.assertIn("python3 tools/test.py", text)
        self.assertIn("512x512/apps/grok-bot.png", text)
        self.assertIn(WATCHER_NAME, text)
        self.assertIn("grok-bot-companion", text)
        self.assertIn("launch", text.lower())

    def test_validate_fails_arch_on_source_failure(self):
        text = read_repo_text(VALIDATE_WORKFLOW_PATH)
        self.assertIn("sha256sum", text)
        self.assertIn("exit 1", text)

    def test_manifest_sources_match_pins(self):
        manifest_text = read_repo_text(MANIFEST_PATH)
        from test_pins import load_pins  # noqa: E402

        pins = load_pins()
        sources = manifest_arch_sources(manifest_text)
        self.assertEqual(set(sources), set(REQUIRED_ARCHES))
        for arch in REQUIRED_ARCHES:
            url, sha256 = sources[arch]
            self.assertEqual(url, pins["architectures"][arch]["url"])
            self.assertEqual(sha256, pins["architectures"][arch]["sha256"])

    def test_publish_gates_on_all_validation(self):
        self.assertTrue(os.path.isfile(PUBLISH_WORKFLOW_PATH))
        text = read_repo_text(PUBLISH_WORKFLOW_PATH)
        self.assertIn("x86_64", text)
        self.assertIn("aarch64", text)
        self.assertIn("success", text)
        for secret in REQUIRED_PUBLISH_SECRETS:
            self.assertIn(f"secrets.{secret}", text)
        self.assertIn("exit 1", text)

    def test_publish_keeps_current_ostree_and_recovers_from_tags(self):
        text = read_repo_text(PUBLISH_WORKFLOW_PATH)
        self.assertIn("prune", text.lower())
        self.assertIn("tag", text.lower())

    def test_publish_rollback_uses_newest_deployed_tag(self):
        text = read_repo_text(PUBLISH_WORKFLOW_PATH)
        self.assertIn("Recover the tagged prior release on failure", text)
        self.assertNotIn("sed -n '2p'", text)
        self.assertNotIn("grep -Fxv", text)
        self.assertIn("flatpak/deployed-*-r*", text)
        self.assertIn("flatpak/deployed-${VERSION}-r${RELEASE_R}", text)
        self.assertIn("--sort=-v:refname", text)
        self.assertIn("--points-at", text)
        self.assertIn('gh release download "${REL_TAG}"', text)

    def test_publish_tag_step_uses_revisioned_tags(self):
        text = read_repo_text(PUBLISH_WORKFLOW_PATH)
        self.assertIn('git tag --list "flatpak/${VERSION}-r*"', text)
        self.assertIn("flatpak/${VERSION}-r${N}", text)
        self.assertIn("N=1", text)
        self.assertIn("+ 1", text)
        self.assertNotIn("refusing silent reuse", text)

    def test_publish_has_concurrency_group(self):
        text = read_repo_text(PUBLISH_WORKFLOW_PATH)
        self.assertIn("group: publish", text)
        self.assertIn("cancel-in-progress: false", text)

    def test_workflows_use_sudo_for_flatpak_system_ops(self):
        for path in (VALIDATE_WORKFLOW_PATH, PUBLISH_WORKFLOW_PATH):
            with self.subTest(path=path):
                text = read_repo_text(path)
                for lineno, line in enumerate(text.splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith("flatpak remote-add") or stripped.startswith("flatpak install"):
                        self.fail(f"{path}:{lineno} runs a system flatpak op without sudo")
                self.assertIn("sudo flatpak remote-add", text)
                self.assertIn("sudo flatpak install", text)


if __name__ == "__main__":
    unittest.main()
