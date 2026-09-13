"""Workspace runner checks: fail-closed parsing plus payload/companion gates.

Phase 1 wires the runner self-checks. Phase 2 adds payload and companion
rejection checks. Phase 3 adds the atomic-release gate checks.
"""

import importlib.util
import os
import re
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

WINDOW_ICON = "/app/grok-bot/grok-bot.png"
ELECTRON_RESOURCE_ICON = "/app/grok-bot/resources/icon.png"
UPSTREAM_PRESERVED_ICON = "/app/grok-bot/resources/icon.upstream.png"
ROUNDED_ICON_SOURCE = "grok-bot-unpacked/resources/icon.png"
APPID_1024_ICON = (
    "/app/share/icons/hicolor/1024x1024/apps/io.github.viniciosrab.GrokBot.png"
)
APPID_HICOLOR_ICON = (
    "/app/share/icons/hicolor/${size}x${size}/apps/io.github.viniciosrab.GrokBot.png"
)
WMCLASS_HICOLOR_ICON = (
    "/app/share/icons/hicolor/${size}x${size}/apps/grok-bot.png"
)
UNPACKED_WMCLASS_HICOLOR_ICON = (
    "/app/grok-bot/usr/share/icons/hicolor/${size}x${size}/apps/grok-bot.png"
)

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
    """Taskbar/window/app-id use 10/11-padded rounded vendor artwork.

    Tray stays on the preserved unpadded original of those same bytes.
    Require SDK ffmpeg with 10/11 inner artwork (not 8/11, not unpadded
    full-canvas). Do not apply the tray 16-on-22 canvas to the taskbar,
    or alias opaque hicolor grok-bot.png onto app-id/window. After
    app-id icons exist, overwrite WM-class grok-bot.png with those same
    padded bytes. Exported app-id icons stop at 512 (flatpak-builder
    export limit).
    """
    if VENDOR_ICON_512 not in manifest_text or VENDOR_HICOLOR_TREE not in manifest_text:
        return False
    if "-name grok-bot.png" in manifest_text:
        return False
    if "8/11" in manifest_text:
        return False
    if "inner=$((size*10/11))" not in manifest_text:
        return False
    if "inner=$((1024*10/11))" not in manifest_text:
        return False
    if "pad=" not in manifest_text:
        return False
    if "inner1024" in manifest_text:
        return False
    if "scale=${size}:${size}:flags=lanczos" in manifest_text:
        return False
    if "/usr/bin/ffmpeg" not in manifest_text:
        return False
    if "test -x /usr/bin/ffmpeg" not in manifest_text:
        return False
    if "[ -x /usr/bin/ffmpeg ]" in manifest_text:
        return False
    if "16 24 32 48 64 128 256 512" not in manifest_text:
        return False
    if not check_exported_sizes_capped_at_512(manifest_text):
        return False
    if not check_rounded_taskbar_copy(manifest_text):
        return False
    if not check_electron_fullsize_resource(manifest_text):
        return False
    if not check_wmclass_hicolor_overwrite(manifest_text):
        return False
    if not check_upstream_preserved(manifest_text):
        return False
    return "io.github.viniciosrab.GrokBot.png" in manifest_text


def check_exported_sizes_capped_at_512(manifest_text):
    """Exported app-id hicolor icons stop at 512, never 1024."""
    if "1024x1024/apps/io.github.viniciosrab.GrokBot.png" in manifest_text:
        return False
    return True


def check_rounded_taskbar_copy(manifest_text):
    """Window and app-id icons use 10/11-padded rounded vendor artwork.

    Opaque vendor hicolor grok-bot.png must not be installed onto app-id
    or window paths. Do not use 8/11 or unpadded full-canvas scale.
    Do not apply the tray 16-on-22 canvas to the taskbar.
    """
    rounded_assign = 'ROUNDED_ICON="%s"' % ROUNDED_ICON_SOURCE
    if rounded_assign not in manifest_text:
        return False
    if "8/11" in manifest_text:
        return False
    if "inner=$((size*10/11))" not in manifest_text:
        return False
    appid_scale = "scale=${inner}:${inner}:flags=lanczos"
    appid_pad = "pad=${size}:${size}:(ow-iw)/2:(oh-ih)/2:color=0x00000000"
    appid_dest = (
        '"/app/share/icons/hicolor/${size}x${size}/apps/io.github.viniciosrab.GrokBot.png"'
    )
    if appid_scale not in manifest_text or appid_dest not in manifest_text:
        return False
    if appid_pad not in manifest_text:
        return False
    if "scale=${size}:${size}:flags=lanczos" in manifest_text:
        return False
    opaque_appid_src = (
        "grok-bot-unpacked/usr/share/icons/hicolor/${size}x${size}/apps/grok-bot.png"
    )
    if opaque_appid_src in manifest_text:
        return False
    if 'install -m644 "${OFFICIAL_512}"' in manifest_text:
        return False
    ffmpeg_appid = False
    for line in manifest_text.splitlines():
        if "pad=22:22" in line or "QSize(22, 22)" in line:
            return False
        if (
            "/usr/bin/ffmpeg" in line
            and appid_scale in line
            and appid_pad in line
            and appid_dest in line
        ):
            ffmpeg_appid = True
    return ffmpeg_appid


def check_electron_fullsize_resource(manifest_text):
    """The Electron window icon is 10/11-padded 1024 artwork."""
    if UPSTREAM_PRESERVED_ICON not in manifest_text:
        return False
    if ELECTRON_RESOURCE_ICON not in manifest_text:
        return False
    if APPID_1024_ICON in manifest_text:
        return False
    if "inner1024" in manifest_text:
        return False
    if "8/11" in manifest_text:
        return False
    if "inner=$((1024*10/11))" not in manifest_text:
        return False
    if "pad=1024:1024" not in manifest_text:
        return False
    if 'install -m644 "${ROUNDED_ICON}" %s' % ELECTRON_RESOURCE_ICON in manifest_text:
        return False
    if 'install -m644 "${ROUNDED_ICON}" %s' % WINDOW_ICON in manifest_text:
        return False
    ffmpeg_resource = False
    ffmpeg_window = False
    for line in manifest_text.splitlines():
        if (
            ELECTRON_RESOURCE_ICON in line
            and "/usr/bin/ffmpeg" in line
            and "pad=1024:1024" in line
        ):
            ffmpeg_resource = True
        if (
            WINDOW_ICON in line
            and "/usr/bin/ffmpeg" in line
            and "pad=1024:1024" in line
        ):
            ffmpeg_window = True
    return ffmpeg_resource and ffmpeg_window


def check_wmclass_hicolor_overwrite(manifest_text):
    """StartupWMClass=grok-bot looks up vendor-named grok-bot.png.

    After app-id padded icons exist, overwrite those vendor-named
    files with the same padded bytes. Do not find-alias or copy
    opaque vendor art onto the WM-class path.
    """
    if "-name grok-bot.png" in manifest_text:
        return False
    opaque_src = (
        "grok-bot-unpacked/usr/share/icons/hicolor/${size}x${size}/apps/grok-bot.png"
    )
    if opaque_src in manifest_text:
        return False
    ffmpeg_appid_line = None
    wmclass_overwrite = False
    unpacked_guard = False
    unpacked_overwrite = False
    for index, line in enumerate(manifest_text.splitlines()):
        if "/usr/bin/ffmpeg" in line and APPID_HICOLOR_ICON in line:
            ffmpeg_appid_line = index
        if (
            "install" in line
            and APPID_HICOLOR_ICON in line
            and WMCLASS_HICOLOR_ICON in line
        ):
            if ffmpeg_appid_line is None or index <= ffmpeg_appid_line:
                return False
            wmclass_overwrite = True
        if "test -f" in line and UNPACKED_WMCLASS_HICOLOR_ICON in line:
            if ffmpeg_appid_line is None or index <= ffmpeg_appid_line:
                return False
            unpacked_guard = True
        if (
            "install" in line
            and APPID_HICOLOR_ICON in line
            and UNPACKED_WMCLASS_HICOLOR_ICON in line
        ):
            if ffmpeg_appid_line is None or index <= ffmpeg_appid_line:
                return False
            unpacked_overwrite = True
    return wmclass_overwrite and unpacked_guard and unpacked_overwrite


def check_upstream_preserved(manifest_text):
    """The original vendor resources/icon.png is preserved before replacement."""
    if UPSTREAM_PRESERVED_ICON not in manifest_text:
        return False
    if "grok-bot-unpacked/resources/icon.png" not in manifest_text:
        return False
    lines = manifest_text.splitlines()
    preserve_line = next(
        (
            index
            for index, line in enumerate(lines)
            if UPSTREAM_PRESERVED_ICON in line
            and "grok-bot-unpacked/resources/icon.png" in line
        ),
        None,
    )
    if preserve_line is None:
        return False
    replace_line = next(
        (
            index
            for index, line in enumerate(lines)
            if ELECTRON_RESOURCE_ICON in line
            and ("install" in line or "ffmpeg" in line or "cp" in line)
            and index > preserve_line
        ),
        None,
    )
    if replace_line is None:
        return False
    return preserve_line < replace_line


def check_tray_prefers_unpadded(companion_src):
    """The tray prefers the preserved unpadded source on a 16-on-22 canvas."""
    if UPSTREAM_PRESERVED_ICON not in companion_src:
        return False
    if "hicolor/24x24/apps/io.github.viniciosrab.GrokBot.png" not in companion_src:
        return False
    if "apps/grok-bot.png" in companion_src:
        return False
    for required in (
        "QSize(22, 22)",
        "QSize(16, 16)",
        "Qt::transparent",
        "drawPixmap",
        "setIconByPixmap",
        "QPainter",
    ):
        if required not in companion_src:
            return False
    return companion_src.index(UPSTREAM_PRESERVED_ICON) < companion_src.index(
        "hicolor/24x24/apps/io.github.viniciosrab.GrokBot.png"
    )


def check_no_find_alias(manifest_text):
    """Reject find-style mass aliasing of grok-bot.png onto the app-id."""
    return "-name grok-bot.png" not in manifest_text


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
    if len(exec_lines) != 1 or "companion" not in exec_lines[0] or "%u" not in exec_lines[0]:
        return False
    if "x-scheme-handler/grokbot" not in desktop_text:
        return False
    if "x-scheme-handler/sand" not in desktop_text:
        return False
    if "X-Flatpak-RenamedFrom=grok-bot.desktop;" not in desktop_text:
        return False
    if "X-KDE-Protocols=grokbot;sand;" not in desktop_text:
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
    companion command, and KF6 SNI lifecycle in the companion.

    The tray prefers preserved icon.upstream.png, scaled 16x16 onto a
    transparent 22x22 QPainter canvas. Do not route the tray through
    hicolor copies, and do not send opaque vendor grok-bot.png to the
    taskbar/window/app-id paths.
    """
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
        "QPainter",
        "QSize(22, 22)",
        "QSize(16, 16)",
        "Qt::transparent",
        "drawPixmap",
        "hicolor/24x24/apps/io.github.viniciosrab.GrokBot.png",
        "/app/grok-bot/resources/icon.png",
        "grokbot:",
        "sand:",
        "forwardProtocolUrls",
        "RuntimeLocation",
        "grok-bot-companion.lock",
    ):
        if required not in companion_src:
            return False
    # Exported app-id icons stop at 512, so the tray must not depend on a
    # 1024 hicolor asset that flatpak-builder refuses to export.
    if "1024x1024/apps/io.github.viniciosrab.GrokBot.png" in companion_src:
        return False
    if not check_tray_prefers_unpadded(companion_src):
        return False
    if "apps/grok-bot.png" in companion_src:
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


def check_native_kde_frame_transform(manifest_text):
    """Packaged Payload patches app.asar so Linux keeps a native KDE frame.

    The helper is fail-closed, runs after the unpacked payload is copied to
    /app, and must not change the Electron wrapper, finish-args, or BaseApp.
    """
    if "path: tools/patch_electron_native_frame.py" not in manifest_text:
        return False
    if (
        "python3 patch_electron_native_frame.py /app/grok-bot/resources/app.asar"
        not in manifest_text
    ):
        return False
    if "Electron2.BaseApp" in manifest_text:
        return False
    if "--ozone-platform" in manifest_text:
        return False
    wrapper = 'zypak-wrapper "/app/grok-bot/%s" --password-store=basic "$@"'
    return wrapper in manifest_text


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
        "native-kde-frame": check_native_kde_frame_transform(manifest_text),
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

    def test_missing_rounded_taskbar_copy_rejects(self):
        self.assertFalse(
            check_vendor_icon(
                "16 24 32 48 64 128 256 512 "
                "io.github.viniciosrab.GrokBot.png "
                "usr/share/icons/hicolor/512x512/apps/grok-bot.png "
                "usr/share/icons/hicolor"
            )
        )

    def test_find_alias_rejects(self):
        self.assertFalse(
            check_vendor_icon(
                "usr/share/icons/hicolor/512x512/apps/grok-bot.png "
                "usr/share/icons/hicolor "
                "16 24 32 48 64 128 256 512 "
                "io.github.viniciosrab.GrokBot.png -name grok-bot.png "
                'ROUNDED_ICON="grok-bot-unpacked/resources/icon.png" '
                "/usr/bin/ffmpeg test -x /usr/bin/ffmpeg "
                "inner=$((size*10/11)) inner=$((1024*10/11)) "
                'scale=${inner}:${inner}:flags=lanczos,'
                "pad=${size}:${size}:(ow-iw)/2:(oh-ih)/2:color=0x00000000 "
                "pad=1024:1024 "
                '"/app/share/icons/hicolor/${size}x${size}/apps/io.github.viniciosrab.GrokBot.png" '
            )
        )

    def test_padded_appid_scale_rejects(self):
        self.assertFalse(
            check_vendor_icon(
                "usr/share/icons/hicolor/512x512/apps/grok-bot.png "
                "usr/share/icons/hicolor "
                "16 24 32 48 64 128 256 512 "
                "io.github.viniciosrab.GrokBot.png "
                'ROUNDED_ICON="grok-bot-unpacked/resources/icon.png" '
                "/usr/bin/ffmpeg test -x /usr/bin/ffmpeg "
                "inner=$((size*8/11)) 8/11 pad= "
                'scale=${inner}:${inner}:flags=lanczos,'
                "pad=${size}:${size}:(ow-iw)/2:(oh-ih)/2:color=0x00000000 "
                '"/app/share/icons/hicolor/${size}x${size}/apps/io.github.viniciosrab.GrokBot.png" '
                "inner1024=$((1024*8/11)) pad=1024:1024 "
                'install -m644 "${ROUNDED_ICON}" /app/grok-bot/grok-bot.png '
                'install -m644 "${ROUNDED_ICON}" /app/grok-bot/resources/icon.png'
            )
        )

    def test_unpadded_full_canvas_rejects(self):
        self.assertFalse(
            check_vendor_icon(
                "usr/share/icons/hicolor/512x512/apps/grok-bot.png "
                "usr/share/icons/hicolor "
                "16 24 32 48 64 128 256 512 "
                "io.github.viniciosrab.GrokBot.png "
                'ROUNDED_ICON="grok-bot-unpacked/resources/icon.png" '
                "/usr/bin/ffmpeg test -x /usr/bin/ffmpeg "
                'scale=${size}:${size}:flags=lanczos '
                '"/app/share/icons/hicolor/${size}x${size}/apps/io.github.viniciosrab.GrokBot.png" '
                'install -m644 "${ROUNDED_ICON}" /app/grok-bot/grok-bot.png '
                'install -m644 "${ROUNDED_ICON}" /app/grok-bot/resources/icon.png'
            )
        )

    def test_opaque_hicolor_appid_copy_rejects(self):
        self.assertFalse(
            check_rounded_taskbar_copy(
                'ROUNDED_ICON="grok-bot-unpacked/resources/icon.png" '
                "/usr/bin/ffmpeg "
                "inner=$((size*10/11)) "
                'scale=${inner}:${inner}:flags=lanczos,'
                "pad=${size}:${size}:(ow-iw)/2:(oh-ih)/2:color=0x00000000 "
                '"/app/share/icons/hicolor/${size}x${size}/apps/io.github.viniciosrab.GrokBot.png" '
                'src="grok-bot-unpacked/usr/share/icons/hicolor/${size}x${size}/apps/grok-bot.png"'
            )
        )

    def test_missing_wmclass_overwrite_rejects(self):
        self.assertFalse(
            check_vendor_icon(
                "16 24 32 48 64 128 256 512 "
                "io.github.viniciosrab.GrokBot.png "
                "usr/share/icons/hicolor/512x512/apps/grok-bot.png "
                "usr/share/icons/hicolor "
                'ROUNDED_ICON="grok-bot-unpacked/resources/icon.png" '
                "install -m644 grok-bot-unpacked/resources/icon.png "
                "/app/grok-bot/resources/icon.upstream.png\n"
                "/usr/bin/ffmpeg "
                "inner=$((size*10/11)) inner=$((1024*10/11)) "
                'scale=${inner}:${inner}:flags=lanczos,'
                "pad=${size}:${size}:(ow-iw)/2:(oh-ih)/2:color=0x00000000 "
                "pad=1024:1024 "
                '"/app/share/icons/hicolor/${size}x${size}/apps/io.github.viniciosrab.GrokBot.png"\n'
                "/usr/bin/ffmpeg pad=1024:1024 /app/grok-bot/resources/icon.png\n"
                "/usr/bin/ffmpeg pad=1024:1024 /app/grok-bot/grok-bot.png"
            )
        )

    def test_wmclass_overwrite_from_opaque_rejects(self):
        self.assertFalse(
            check_wmclass_hicolor_overwrite(
                "/usr/bin/ffmpeg "
                '"/app/share/icons/hicolor/${size}x${size}/apps/io.github.viniciosrab.GrokBot.png"\n'
                "install -m644 "
                '"grok-bot-unpacked/usr/share/icons/hicolor/${size}x${size}/apps/grok-bot.png" '
                '"/app/share/icons/hicolor/${size}x${size}/apps/grok-bot.png"\n'
                'test -f "/app/grok-bot/usr/share/icons/hicolor/${size}x${size}/apps/grok-bot.png"\n'
                "install -m644 "
                '"grok-bot-unpacked/usr/share/icons/hicolor/${size}x${size}/apps/grok-bot.png" '
                '"/app/grok-bot/usr/share/icons/hicolor/${size}x${size}/apps/grok-bot.png"'
            )
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


class IconSeparationContractTests(unittest.TestCase):
    """Taskbar/window use 10/11-padded artwork; tray keeps 16-on-22.

    WM-class grok-bot.png in exported hicolor must be overwritten with the
    same padded app-id bytes after those icons exist. Do not apply the
    tray canvas to the taskbar, and do not use 8/11 or unpadded full-canvas.
    """

    def test_rounded_copy_for_app_id_window_and_resource(self):
        manifest_text = read_repo_text(MANIFEST_PATH)
        self.assertTrue(check_rounded_taskbar_copy(manifest_text))
        self.assertTrue(check_electron_fullsize_resource(manifest_text))
        self.assertIn("16 24 32 48 64 128 256 512", manifest_text)
        self.assertNotIn("8/11", manifest_text)
        self.assertIn("inner=$((size*10/11))", manifest_text)
        self.assertIn("inner=$((1024*10/11))", manifest_text)
        self.assertIn("pad=", manifest_text)
        self.assertIn("pad=1024:1024", manifest_text)
        self.assertNotIn("inner=$((size*8/11))", manifest_text)
        self.assertNotIn("scale=${size}:${size}:flags=lanczos", manifest_text)
        self.assertIn("scale=${inner}:${inner}:flags=lanczos", manifest_text)
        self.assertNotIn("pad=22:22", manifest_text)
        self.assertIn(UPSTREAM_PRESERVED_ICON, manifest_text)
        self.assertNotIn(
            "grok-bot-unpacked/usr/share/icons/hicolor/${size}x${size}/apps/grok-bot.png",
            manifest_text,
        )

    def test_original_upstream_source_preserved_before_resource_replace(self):
        manifest_text = read_repo_text(MANIFEST_PATH)
        self.assertTrue(check_upstream_preserved(manifest_text))

    def test_exported_app_id_sizes_stop_at_512(self):
        manifest_text = read_repo_text(MANIFEST_PATH)
        self.assertTrue(check_exported_sizes_capped_at_512(manifest_text))
        self.assertNotIn(
            "1024x1024/apps/io.github.viniciosrab.GrokBot.png", manifest_text
        )

    def test_tray_prefers_preserved_unpadded_source(self):
        companion_src = read_repo_text(COMPANION_SRC)
        self.assertTrue(check_tray_prefers_unpadded(companion_src))
        self.assertNotIn(
            "1024x1024/apps/io.github.viniciosrab.GrokBot.png", companion_src
        )
        for required in (
            "QPainter",
            "QSize(22, 22)",
            "QSize(16, 16)",
            "Qt::transparent",
            "drawPixmap",
            UPSTREAM_PRESERVED_ICON,
        ):
            self.assertIn(required, companion_src)
        self.assertNotIn("apps/grok-bot.png", companion_src)

    def test_no_find_alias(self):
        manifest_text = read_repo_text(MANIFEST_PATH)
        self.assertTrue(check_no_find_alias(manifest_text))

    def test_wmclass_hicolor_overwrite_matches_appid(self):
        manifest_text = read_repo_text(MANIFEST_PATH)
        self.assertTrue(check_wmclass_hicolor_overwrite(manifest_text))
        self.assertIn(WMCLASS_HICOLOR_ICON, manifest_text)
        self.assertIn(UNPACKED_WMCLASS_HICOLOR_ICON, manifest_text)
        self.assertNotIn("-name grok-bot.png", manifest_text)
        self.assertNotIn(
            "grok-bot-unpacked/usr/share/icons/hicolor/${size}x${size}/apps/grok-bot.png",
            manifest_text,
        )


class ProtocolHandoffContractTests(unittest.TestCase):
    """Custom-scheme XDG/Flatpak handoff must be advertised and forwarded."""

    def test_desktop_registers_schemes_and_replaces_vendor_desktop(self):
        desktop_text = read_repo_text(DESKTOP_PATH)
        self.assertIn("MimeType=x-scheme-handler/grokbot;x-scheme-handler/sand;", desktop_text)
        self.assertIn("X-Flatpak-RenamedFrom=grok-bot.desktop;", desktop_text)
        self.assertIn("X-KDE-Protocols=grokbot;sand;", desktop_text)
        self.assertIn("Exec=/app/bin/grok-bot-companion %u", desktop_text)
        for line in desktop_text.splitlines():
            self.assertFalse(line.startswith(" "), line)

    def test_metainfo_provides_scheme_mediatypes(self):
        text = read_repo_text(METAINFO_PATH)
        self.assertIn("<mediatype>x-scheme-handler/grokbot</mediatype>", text)
        self.assertIn("<mediatype>x-scheme-handler/sand</mediatype>", text)

    def test_companion_lock_uses_runtime_dir(self):
        companion_src = read_repo_text(COMPANION_SRC)
        self.assertIn("RuntimeLocation", companion_src)
        self.assertIn("grok-bot-companion.lock", companion_src)
        self.assertLess(
            companion_src.index("RuntimeLocation"),
            companion_src.index("grok-bot-companion.lock"),
        )
        self.assertIn("forwardProtocolUrls", companion_src)
        self.assertIn("return 0", companion_src)

    def test_cold_start_does_not_pass_protocol_urls_to_initial_startchild(self):
        companion_src = read_repo_text(COMPANION_SRC)
        self.assertNotIn("startChild(protocolUrls)", companion_src)
        self.assertNotIn("<< protocolUrls", companion_src)
        self.assertNotIn("setArguments(protocolUrls)", companion_src)
        start_idx = companion_src.index("void start(const QStringList &protocolUrls")
        start_child_idx = companion_src.index("startChild();", start_idx)
        self.assertLess(start_idx, start_child_idx)
        self.assertIn("void startChild()", companion_src)

    def test_cold_urls_forwarded_after_child_start_via_single_instance(self):
        companion_src = read_repo_text(COMPANION_SRC)
        self.assertIn("QProcess::started", companion_src)
        self.assertIn("QTimer::singleShot", companion_src)
        self.assertIn("electronSingleInstanceReady", companion_src)
        self.assertIn("unixSocketIsLive", companion_src)
        self.assertIn("isSymLink", companion_src)
        self.assertIn("SingletonSocket", companion_src)
        self.assertIn("GenericConfigLocation", companion_src)
        self.assertIn('"Grok Bot"', companion_src)
        self.assertIn("forwardProtocolUrls(m_electronCommand, m_pendingProtocolUrls)", companion_src)
        self.assertIn("single-instance", companion_src)
        self.assertNotIn("kColdProtocolDeliveryDelayMs", companion_src)
        self.assertLess(
            companion_src.index("QProcess::started"),
            companion_src.index("deliverColdProtocolUrls"),
        )
        ready_idx = companion_src.index("electronSingleInstanceReady")
        forward_idx = companion_src.index(
            "forwardProtocolUrls(m_electronCommand, m_pendingProtocolUrls)"
        )
        self.assertLess(ready_idx, forward_idx)

    def test_protocol_forwarding_is_bounded_non_blocking_and_does_not_log_urls(self):
        companion_src = read_repo_text(COMPANION_SRC)
        poll = int(re.search(r"kColdProtocolSocketPollMs = (\d+)", companion_src).group(1))
        timeout = int(
            re.search(r"kColdProtocolReadyTimeoutMs = (\d+)", companion_src).group(1)
        )
        self.assertGreater(timeout, poll)
        self.assertGreaterEqual(timeout, 1000)
        self.assertLessEqual(timeout, 30000)
        self.assertIn("QTimer::singleShot", companion_src)
        self.assertIn("hasExpired", companion_src)
        self.assertIn("AF_UNIX", companion_src)
        self.assertNotIn("kMaxColdProtocolDeliveryAttempts", companion_src)
        self.assertNotIn("while (true)", companion_src)
        self.assertEqual(companion_src.count("waitForStarted"), 1)
        self.assertLess(
            companion_src.index("terminateChildGroup"),
            companion_src.index("waitForStarted"),
        )
        self.assertNotIn("qPrintable(urls)", companion_src)
        self.assertNotIn("qPrintable(protocolUrls)", companion_src)
        self.assertNotIn("qPrintable(m_pendingProtocolUrls)", companion_src)
        self.assertIn('failed to deliver protocol URL"', companion_src)
        self.assertNotRegex(
            companion_src,
            r'qWarning\([^)]*%s[^)]*urls',
        )
        self.assertNotRegex(
            companion_src,
            r'qWarning\([^)]*(grokbot:|sand:)',
        )

    def test_warm_losing_lock_forwarding_remains(self):
        companion_src = read_repo_text(COMPANION_SRC)
        lock_fail = companion_src.index("!instanceLock.tryLock()")
        forward = companion_src.index("forwardProtocolUrls(resolveElectronCommand(app), protocolUrls)")
        ret = companion_src.index("return 0;", forward)
        self.assertLess(lock_fail, forward)
        self.assertLess(forward, ret)

    def test_callback_schemes_remain_grokbot_and_sand(self):
        companion_src = read_repo_text(COMPANION_SRC)
        desktop_text = read_repo_text(DESKTOP_PATH)
        self.assertIn('QLatin1String("grokbot:")', companion_src)
        self.assertIn('QLatin1String("sand:")', companion_src)
        self.assertIn("MimeType=x-scheme-handler/grokbot;x-scheme-handler/sand;", desktop_text)

    def test_tray_icon_contracts_remain_untouched(self):
        companion_src = read_repo_text(COMPANION_SRC)
        for required in (
            UPSTREAM_PRESERVED_ICON,
            "QPainter",
            "QSize(22, 22)",
            "QSize(16, 16)",
            "Qt::transparent",
            "drawPixmap",
            "setIconByPixmap",
        ):
            self.assertIn(required, companion_src)
        self.assertNotIn("apps/grok-bot.png", companion_src)

    def test_missing_renamed_from_rejects_electron_exec(self):
        desktop = (
            "Exec=/app/bin/grok-bot-companion %u\n"
            "Icon=io.github.viniciosrab.GrokBot\n"
            "StartupWMClass=grok-bot\n"
            "MimeType=x-scheme-handler/grokbot;x-scheme-handler/sand;\n"
        )
        self.assertFalse(
            check_electron_exec(
                "Exec exit 1 --password-store=basic "
                "CHROME_DESKTOP=io.github.viniciosrab.GrokBot.desktop",
                desktop,
            )
        )


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
        self.assertIn("512x512/apps/io.github.viniciosrab.GrokBot.png", text)
        self.assertIn("1024x1024/apps/io.github.viniciosrab.GrokBot.png", text)
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
