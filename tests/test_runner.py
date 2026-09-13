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

# Pinned zypak module: the gitlink already pins its nickle submodule, so
# flatpak-builder checks it out automatically with no extra source.
ZYPAK_URL = "https://github.com/refi64/zypak.git"
ZYPAK_TAG = "v2025.09"
ZYPAK_COMMIT = "693a71c5ffa80ec9c9ce2ae03b1ccc493c698e53"

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
    if VENDOR_ICON_512 not in manifest_text or VENDOR_HICOLOR_TREE not in manifest_text:
        return False
    # Flatpak exports only app-id-named icons; alias every vendor size.
    if "-name grok-bot.png" not in manifest_text:
        return False
    return "io.github.viniciosrab.GrokBot.png" in manifest_text


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
    if icon_lines != ["Icon=io.github.viniciosrab.GrokBot"]:
        return False
    wm_class_lines = [
        line.strip()
        for line in desktop_text.splitlines()
        if line.strip().startswith("StartupWMClass=")
    ]
    if wm_class_lines != ["StartupWMClass=grok-bot"]:
        return False
    if "--password-store=basic" not in manifest_text:
        return False
    return "CHROME_DESKTOP=io.github.viniciosrab.GrokBot.desktop" in manifest_text


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
        'setIconByName(QStringLiteral("io.github.viniciosrab.GrokBot"))',
        "setIconByPixmap",
        "QSize(22, 22)",
        "hicolor/24x24/apps/io.github.viniciosrab.GrokBot.png",
    ):
        if required not in companion_src:
            return False
    if "killpg" not in companion_src and "setsid" not in companion_src:
        return False
    return True


def check_zypak_submodule_without_redundant_overlay(manifest_text):
    """Pinned zypak relies on automatic submodule checkout for nickle.

    The zypak gitlink already pins its nickle submodule, so declaring a
    second git source overlaid at `path: nickle` collides with the
    submodule checkout and fails the module build.
    """
    for required in (ZYPAK_URL, ZYPAK_TAG, ZYPAK_COMMIT):
        if required not in manifest_text:
            return False
    for line in manifest_text.splitlines():
        if line.strip() == "path: nickle":
            return False
    if "nickle.git" in manifest_text:
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
        "zypak-submodule": check_zypak_submodule_without_redundant_overlay(
            manifest_text
        ),
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


class ZypakSubmoduleContractTests(unittest.TestCase):
    """Pinned zypak uses automatic submodule checkout, never a nickle overlay."""

    def test_redundant_nickle_overlay_rejects(self):
        pinned = f"url: {ZYPAK_URL}\ntag: {ZYPAK_TAG}\ncommit: {ZYPAK_COMMIT}\n"
        self.assertTrue(check_zypak_submodule_without_redundant_overlay(pinned))
        overlay = pinned + "url: https://github.com/refi64/nickle.git\npath: nickle\n"
        self.assertFalse(check_zypak_submodule_without_redundant_overlay(overlay))

    def test_manifest_keeps_pin_without_nickle_overlay(self):
        manifest_text = read_repo_text(MANIFEST_PATH)
        self.assertTrue(
            check_zypak_submodule_without_redundant_overlay(manifest_text)
        )
        for pinned in (ZYPAK_URL, ZYPAK_TAG, ZYPAK_COMMIT):
            self.assertIn(pinned, manifest_text)


VALIDATE_WORKFLOW_PATH = os.path.join(
    REPO_ROOT, ".github", "workflows", "validate.yml"
)
X3_WORKFLOW_PATH = os.path.join(
    REPO_ROOT, ".github", "workflows", "x3.yml"
)
PUBLISH_WORKFLOW_PATH = os.path.join(
    REPO_ROOT, ".github", "workflows", "publish.yml"
)
PROVE_X3_SCRIPT_PATH = os.path.join(REPO_ROOT, "tools", "prove_x3.sh")
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

    def test_validate_has_no_positive_x3_proof(self):
        text = read_repo_text(VALIDATE_WORKFLOW_PATH)
        self.assertNotIn("prove_x3", text)
        self.assertIn("NOT X3 launch proof", text)

    def test_validate_negative_gate_uses_offscreen_and_fails_closed(self):
        text = read_repo_text(VALIDATE_WORKFLOW_PATH)
        self.assertIn("QT_QPA_PLATFORM", text)
        self.assertIn("offscreen", text)
        self.assertIn(WATCHER_NAME, text)
        self.assertIn('test "${RC}" -eq 1', text)

    def test_x3_workflow_is_automatic_hosted_dual_arch_fail_closed(self):
        self.assertTrue(os.path.isfile(X3_WORKFLOW_PATH))
        text = read_repo_text(X3_WORKFLOW_PATH)
        self.assertIn("workflows: [validate]", text)
        self.assertIn("types: [completed]", text)
        self.assertIn("branches: [main]", text)
        self.assertIn("workflow_run", text)
        self.assertIn("workflow_dispatch", text)
        self.assertNotIn("pull_request", text)
        self.assertNotIn("push:", text)
        self.assertIn("ubuntu-24.04-arm", text)
        self.assertIn("ubuntu-24.04", text)
        self.assertIn("x86_64", text)
        self.assertIn("aarch64", text)
        self.assertIn("github.event_name == 'workflow_dispatch'", text)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", text)
        self.assertIn("github.event.workflow_run.event == 'push'", text)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", text)
        self.assertIn("github.event.workflow_run.head_sha || github.sha", text)
        self.assertIn("head_branch", text)
        self.assertIn("conclusion", text)
        self.assertIn("success", text)
        self.assertIn("plasma-workspace", text)
        self.assertIn("xvfb", text)
        self.assertIn("dbus-x11", text)
        self.assertIn("kactivitymanagerd", text)
        self.assertIn("gate:", text)
        self.assertIn("Fail closed on unexpected validate trigger", text)
        self.assertIn("TRIGGER_CONCLUSION", text)
        self.assertIn("TRIGGER_EVENT", text)
        self.assertIn("TRIGGER_BRANCH", text)
        self.assertIn("failing closed", text)
        self.assertIn("exit 1", text)
        self.assertNotIn("continue-on-error: true", text)
        self.assertEqual(text.count("bash tools/prove_x3.sh"), 2)

    def test_prove_x3_script_holds_fail_closed_invariants(self):
        self.assertTrue(
            os.path.isfile(PROVE_X3_SCRIPT_PATH),
            "tools/prove_x3.sh must exist as the single shared X3 proof",
        )
        text = read_repo_text(PROVE_X3_SCRIPT_PATH)
        self.assertIn("plasmashell", text)
        self.assertIn("kactivitymanagerd", text)
        self.assertIn("org.kde.ActivityManager", text)
        self.assertIn("org.kde.ActivityManager.service", text)
        self.assertIn("KAMD_BIN", text)
        self.assertIn("activity_owned", text)
        self.assertIn("kded5", text)
        self.assertIn("org.kde.kded5", text)
        self.assertIn("org.kde.kded5.service", text)
        self.assertIn("KDED_BIN", text)
        self.assertIn("KDED_PID", text)
        self.assertIn("kded_owned", text)
        self.assertIn("kded_load_watcher", text)
        self.assertIn("loadModule", text)
        self.assertIn("statusnotifierwatcher", text)
        self.assertIn("kded.log", text)
        self.assertIn("Xvfb", text)
        self.assertIn("DISPLAY", text)
        self.assertIn("dbus-run-session", text)
        self.assertIn("prove_x3", text)
        self.assertIn("watcher_owned", text)
        self.assertIn("busctl", text)
        self.assertIn("gdbus", text)
        self.assertIn("dbus-send", text)
        self.assertIn("get-name-owner", text)
        self.assertIn("GetNameOwner", text)
        self.assertNotIn("ListNames", text)
        self.assertNotIn("[D-BUS Service]", text)
        self.assertNotIn("fake", text.lower())
        self.assertNotIn("mock", text.lower())
        self.assertIn(WATCHER_NAME, text)
        self.assertIn("UNPROVEN", text)
        self.assertIn("exit 1", text)
        self.assertIn("grok-bot-companion", text)
        self.assertIn("companion_alive", text)
        self.assertIn("/proc/", text)
        self.assertIn("ps -o stat=", text)
        self.assertIn("setsid", text)
        self.assertIn("cleanup_group", text)
        self.assertIn("ps -o pgid=", text)
        self.assertIn('kill -TERM -"${pgid}"', text)
        self.assertIn('kill -KILL -"${pgid}"', text)
        self.assertIn('wait "${pid}"', text)
        self.assertIn("rc=$?", text)
        self.assertIn("seq 1 8", text)
        kded_start = text.index("KDED_BIN")
        plasma_start = text.index("plasmashell --no-respawn")
        watcher_wait = text.index("WATCHER_OK=0")
        self.assertLess(kded_start, plasma_start)
        self.assertLess(plasma_start, watcher_wait)

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
        self.assertIn("workflows: [x3]", text)
        self.assertNotIn("workflows: [validate]", text)
        self.assertIn("types: [completed]", text)
        self.assertIn("branches: [main]", text)
        self.assertIn("x86_64", text)
        self.assertIn("aarch64", text)
        self.assertIn("success", text)
        self.assertIn("workflow_run", text)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", text)
        self.assertIn("event == 'workflow_run'", text)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", text)
        self.assertIn("head_branch", text)
        self.assertIn("head_sha", text)
        self.assertNotIn("event == 'workflow_dispatch'", text)
        self.assertNotIn("event == 'push'", text)
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
        for path in (VALIDATE_WORKFLOW_PATH, X3_WORKFLOW_PATH, PUBLISH_WORKFLOW_PATH):
            with self.subTest(path=path):
                text = read_repo_text(path)
                for lineno, line in enumerate(text.splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith("flatpak remote-add") or stripped.startswith("flatpak install"):
                        self.fail(f"{path}:{lineno} runs a system flatpak op without sudo")
                self.assertIn("sudo flatpak remote-add", text)
                self.assertIn("sudo flatpak install", text)


class PublishTransportContractTests(unittest.TestCase):
    """Publish bootstrap/rollback contract: refs/remotes restore plus first-release no-op."""

    def test_publish_restores_refs_remotes_for_both_arches_before_import(self):
        text = read_repo_text(PUBLISH_WORKFLOW_PATH)
        loop_idx = text.index("for arch in x86_64 aarch64")
        mkdir_idx = text.index('mkdir -p "${dir}/refs/remotes"')
        first_pull_idx = text.index(
            "ostree pull-local --repo=site arch-repos/repo-x86_64"
        )
        second_pull_idx = text.index(
            "ostree pull-local --repo=site arch-repos/repo-aarch64"
        )
        self.assertLess(loop_idx, mkdir_idx)
        self.assertLess(mkdir_idx, first_pull_idx)
        self.assertLess(mkdir_idx, second_pull_idx)
        self.assertLess(first_pull_idx, second_pull_idx)

    def test_publish_validates_arch_repos_fail_closed_before_import(self):
        text = read_repo_text(PUBLISH_WORKFLOW_PATH)
        dir_idx = text.index('test -d "${dir}"')
        config_idx = text.index('test -f "${dir}/config"')
        heads_idx = text.index('test -d "${dir}/refs/heads"')
        mkdir_idx = text.index('mkdir -p "${dir}/refs/remotes"')
        first_pull_idx = text.index(
            "ostree pull-local --repo=site arch-repos/repo-x86_64"
        )
        self.assertLess(dir_idx, mkdir_idx)
        self.assertLess(config_idx, mkdir_idx)
        self.assertLess(heads_idx, mkdir_idx)
        self.assertLess(mkdir_idx, first_pull_idx)
        for marker in (
            "missing arch repo",
            "malformed arch repo",
            "missing config",
            "missing refs/heads",
            "exit 1",
        ):
            self.assertIn(marker, text)

    def test_publish_rollback_first_release_noop_skips_deploy(self):
        text = read_repo_text(PUBLISH_WORKFLOW_PATH)
        recover_idx = text.index("id: recover")
        message_idx = text.index("first release: no prior deployment")
        false_idx = text.index('echo "recovered=false"')
        exit_idx = text.index("exit 0", message_idx)
        true_idx = text.index('echo "recovered=true"')
        self.assertLess(recover_idx, message_idx)
        self.assertLess(message_idx, false_idx)
        self.assertLess(false_idx, exit_idx)
        self.assertLess(exit_idx, true_idx)
        lowered = text.lower()
        self.assertIn("first release", lowered)
        self.assertIn("no prior deployment", lowered)
        self.assertIn("GITHUB_OUTPUT", text)
        self.assertEqual(
            text.count("steps.recover.outputs.recovered == 'true'"), 2
        )
        upload_idx = text.index("Upload the recovered site for rollback")
        deploy_idx = text.index("Publish the recovered site to Pages")
        first_cond_idx = text.index(
            "steps.recover.outputs.recovered == 'true'"
        )
        second_cond_idx = text.index(
            "steps.recover.outputs.recovered == 'true'",
            first_cond_idx + 1,
        )
        self.assertLess(recover_idx, upload_idx)
        self.assertLess(upload_idx, deploy_idx)
        self.assertLess(recover_idx, first_cond_idx)
        self.assertLess(first_cond_idx, second_cond_idx)


if __name__ == "__main__":
    unittest.main()
