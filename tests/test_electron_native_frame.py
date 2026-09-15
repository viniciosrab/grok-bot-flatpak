"""Fail-closed packed app.asar transform: native KDE frame, close-to-hide
lifecycle, second-instance reveal, and hidden menu bar."""

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL_PATH = os.path.join(REPO_ROOT, "tools", "patch_electron_native_frame.py")
MANIFEST_PATH = os.path.join(REPO_ROOT, "io.github.viniciosrab.GrokBot.yml")
TEST_RUNNER_PATH = os.path.join(REPO_ROOT, "tests", "test_runner.py")

LINUX_FRAMELESS = (
    'function Gx(e){return e.isMac?{frame:!0,titleBarStyle:"hiddenInset",'
    'trafficLightPosition:Ix}:e.isWindows?{frame:!1,titleBarStyle:"hidden",'
    "titleBarOverlay:Bx(e.backgroundColor)}:{frame:!1,titleBarStyle:\"default\"}}"
)
LINUX_NATIVE = LINUX_FRAMELESS.replace(
    '{frame:!1,titleBarStyle:"default"}',
    '{frame:!0,titleBarStyle:"default"}',
)
LINUX_CONTROLS = (
    'if(c==="darwin")return null;if(c==="win32"){return hidden}'
    "if(o)return null;let C,T,E,R,M;if(e[15]!==r){drawButtons()}"
)
LINUX_CONTROLS_HIDDEN = LINUX_CONTROLS.replace(
    "if(o)return null;let C,T,E,R,M;if(e[15]!==r)",
    "if(1)return null;let C,T,E,R,M;if(e[15]!==r)",
)
# Byte-exact vendor creation site from the packed main-process bundle:
# the documented `autoHideMenuBar` option is inserted right after the
# window-options spread of the single BrowserWindow construction.
WINDOW_CREATE_UPSTREAM = (
    'i=new rs.BrowserWindow({...a.windowOptions,title:rs.app.getName(),'
    'icon:Yx({platform:process.platform,isPackaged:rs.app.isPackaged,'
    'resourcesPath:process.resourcesPath,devIconPath:t}),backgroundColor:e,'
    '...Gx({isMac:o,isWindows:process.platform==="win32",backgroundColor:e}),'
    'webPreferences:{contextIsolation:!0,nodeIntegration:!1,'
    'preload:Sp.default.join(dy,fp({isPackaged:rs.app.isPackaged,'
    'devCapability:r})),sandbox:!0,webviewTag:!0}})'
)
WINDOW_CREATE_PATCHED = (
    'i=new rs.BrowserWindow({...a.windowOptions,autoHideMenuBar:!0,'
    'title:rs.app.getName(),'
    'icon:Yx({platform:process.platform,isPackaged:rs.app.isPackaged,'
    'resourcesPath:process.resourcesPath,devIconPath:t}),backgroundColor:e,'
    '...Gx({isMac:o,isWindows:process.platform==="win32",backgroundColor:e}),'
    'webPreferences:{contextIsolation:!0,nodeIntegration:!1,'
    'preload:Sp.default.join(dy,fp({isPackaged:rs.app.isPackaged,'
    'devCapability:r})),sandbox:!0,webviewTag:!0}})'
)
# Byte-exact vendor close shape from the packed main-process bundle: the
# existing `closed` listener stays and a `close` interceptor is appended.
CLOSE_UPSTREAM = 's.on("closed",()=>{Ch.markRendererNotReady()})'
CLOSE_PATCHED = (
    's.on("closed",()=>{Ch.markRendererNotReady()}),'
    's.on("close",e=>{he.app.quitting||(e.preventDefault(),s.hide())})'
)
# Byte-exact vendor quit line from the same bundle: a one-shot
# `before-quit` listener is prepended and the quit line itself is kept.
ARM_UPSTREAM = (
    'he.app.on("window-all-closed",()=>{process.platform!=="darwin"'
    '&&he.app.quit()})'
)
ARM_PATCHED = (
    'he.app.once("before-quit",()=>{he.app.quitting=!0}),'
    'he.app.on("window-all-closed",()=>{process.platform!=="darwin"'
    '&&he.app.quit()})'
)
# Byte-exact vendor activation shape from the packed main-process bundle:
# the handler reveals only on the empty-argv path and merely handles
# links otherwise. The patched shape reveals on every activation.
SECOND_INSTANCE_UPSTREAM = (
    's=(c,l)=>{let d=Ph(r,l);if(d.length===0){t.focus();return}'
    'for(let u of d)o.handleCandidate(u,"second-instance")}'
)
SECOND_INSTANCE_PATCHED = (
    's=(c,l)=>{let d=Ph(r,l);t.focus();if(d.length!==0)'
    'for(let u of d)o.handleCandidate(u,"second-instance")};;;;;;;;'
)
# Byte-exact vendor single-instance shape from the packed main-process
# bundle: a SIGTERM-to-quit bridge is appended so an OS SIGTERM reaches
# graceful app.quit cleanup instead of killing Electron raw.
SIGTERM_UPSTREAM = 'ru||he.app.quit();'
SIGTERM_PATCHED = 'ru||he.app.quit();process.on("SIGTERM",()=>{he.app.quit()});'
# Byte-exact vendor hardware-acceleration relaunch from
# dist/electron-main/main-app.cjs: quit() after relaunch() is aborted by
# vendor before-quit preventDefault, so the process stays alive. Same-length
# swap to exit() actually terminates this instance. Window X still hides.
RELAUNCH_UPSTREAM = 'ye.app.relaunch(),ye.app.quit()'
RELAUNCH_PATCHED = 'ye.app.relaunch(),ye.app.exit()'
RELAUNCH_CONTEXT_UPSTREAM = (
    'hardwareAccelerationEnabledAtLaunch:SFt,'
    'relaunchDesktop:()=>{let B=re.environment.restartExitCode;'
    'if(B!=null){N4(B);return}ye.app.relaunch(),ye.app.quit()},'
    'getMachineId:()=>tt()'
)
RELAUNCH_CONTEXT_PATCHED = RELAUNCH_CONTEXT_UPSTREAM.replace(
    RELAUNCH_UPSTREAM, RELAUNCH_PATCHED
)
# Byte-exact vendor focus chain proving the focus target reveals a hidden
# window (restore when minimized, show, then focus), not a bare focus.
FOCUS_CHAIN = (
    'function hye(){if(Ac.focusMainWindow!==void 0){Ac.focusMainWindow();return}'
    'let e=xh;e==null||e.isDestroyed()||(e.isMinimized()&&e.restore(),e.show(),e.focus())}'
)
UNRELATED = 'other:{frame:!1,titleBarStyle:"hidden"} keep me'
FULL_CORE_UPSTREAM = (
    LINUX_FRAMELESS + WINDOW_CREATE_UPSTREAM + SIGTERM_UPSTREAM
    + CLOSE_UPSTREAM + ARM_UPSTREAM + SECOND_INSTANCE_UPSTREAM + FOCUS_CHAIN
)
FULL_CORE_PATCHED = (
    LINUX_NATIVE + WINDOW_CREATE_PATCHED + SIGTERM_PATCHED
    + CLOSE_PATCHED + ARM_PATCHED + SECOND_INSTANCE_PATCHED + FOCUS_CHAIN
)

# Representative Sand 0.51.0 shapes observed in the downloaded x86_64
# AppImage. The stable syntax is retained while ordinary minifier identifiers
# differ from the legacy fixture above.
MODERN_LINUX_FRAMELESS = (
    'function rP(e){return e.isMac?{frame:!0,titleBarStyle:"hiddenInset",'
    'trafficLightPosition:YI}:e.isWindows?{frame:!1,titleBarStyle:"hidden",'
    'titleBarOverlay:tP(e.backgroundColor)}:{frame:!1,titleBarStyle:"default"}}'
)
MODERN_LINUX_CONTROLS = (
    'if(c==="darwin")return null;if(c==="win32"){let W;return W}'
    'if(o)return null;let C,A,E,R,N;if(e[15]!==r){drawButtons()}'
)
MODERN_WINDOW_CREATE_UPSTREAM = (
    'i=new is.BrowserWindow({...a.windowOptions,title:is.app.getName(),'
    'webPreferences:{sandbox:!0}})'
)
MODERN_CLOSE_UPSTREAM = (
    's.on("closed",()=>{Dh.markRendererNotReady()});let c=AP({window:TP(s),'
    'app:{onceBeforeQuit:d=>he.app.once("before-quit",d)}})'
)
MODERN_ARM_UPSTREAM = (
    'he.app.on("window-all-closed",()=>{process.platform!=="darwin"'
    '&&he.app.quit()})'
)
MODERN_SECOND_INSTANCE_UPSTREAM = (
    's=(c,l)=>{let d=Mh(r,l);if(d.length===0){t.focus();return}'
    'for(let u of d)o.handleCandidate(u,"second-instance")}'
)
MODERN_SIGTERM_UPSTREAM = (
    'var su=!he.app.isPackaged||he.app.requestSingleInstanceLock();'
    'su||he.app.quit();'
)
MODERN_CORE_UPSTREAM = (
    MODERN_LINUX_FRAMELESS + MODERN_WINDOW_CREATE_UPSTREAM
    + MODERN_SIGTERM_UPSTREAM + MODERN_CLOSE_UPSTREAM
    + MODERN_ARM_UPSTREAM + MODERN_SECOND_INSTANCE_UPSTREAM + FOCUS_CHAIN
)
MODERN_RELAUNCH_CONTEXT_UPSTREAM = (
    'hardwareAccelerationEnabledAtLaunch:SK,relaunchDesktop:()=>{let B='
    'ne.environment.restartExitCode;if(B!=null){zZ(B);return}'
    'me.app.relaunch(),me.app.quit()},getMachineId:()=>it()'
)


def load_tool():
    spec = importlib.util.spec_from_file_location("patch_electron_native_frame", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_runner_tests():
    spec = importlib.util.spec_from_file_location("payload_test_runner", TEST_RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_asar(tool, extra=None):
    files = {
        "dist/electron-main/main-core.cjs": FULL_CORE_UPSTREAM.encode("utf-8"),
        "dist/electron-main/main-app.cjs": RELAUNCH_CONTEXT_UPSTREAM.encode("utf-8"),
        "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode("utf-8"),
        "keep/other.cjs": UNRELATED.encode("utf-8"),
    }
    if extra:
        files.update(extra)
    return tool.write_asar(files)


def sample_modern_asar(tool, extra=None):
    files = {
        "dist/electron-main/main-core.cjs": MODERN_CORE_UPSTREAM.encode("utf-8"),
        "dist/electron-main/main-app.cjs": MODERN_RELAUNCH_CONTEXT_UPSTREAM.encode(
            "utf-8"
        ),
        "dist/renderer/assets/index-B7CuLxVI.js": MODERN_LINUX_CONTROLS.encode(
            "utf-8"
        ),
    }
    if extra:
        files.update(extra)
    return tool.write_asar(files)


def sample_future_structural_asar(tool, extra=None):
    """Represent a reviewed-but-not-yet-pinned minifier rename."""
    files = {
        "dist/electron-main/main-core.cjs": MODERN_CORE_UPSTREAM.encode("utf-8"),
        "dist/electron-main/main-app.cjs": MODERN_RELAUNCH_CONTEXT_UPSTREAM.encode(
            "utf-8"
        ),
        "dist/renderer/assets/index-B7CuLxVI.js": MODERN_LINUX_CONTROLS.replace(
            "if(o)return null", "if(q)return null"
        ).encode("utf-8"),
    }
    if extra:
        files.update(extra)
    return tool.write_asar(files)


class NativeFrameTransformTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()

    def test_patch_pairs_are_well_formed(self):
        for find, replace in self.tool.PATCHES + self.tool.EXTENSIONS:
            self.assertIsInstance(find, bytes)
            self.assertIsInstance(replace, bytes)
            self.assertTrue(find)
            self.assertNotEqual(find, replace)
        for find, replace in self.tool.EXTENSIONS:
            self.assertIn(
                find,
                replace,
                "extension replacements must preserve their anchor",
            )

    def test_native_frame_without_wco_and_without_in_content_controls(self):
        blob = sample_asar(self.tool)
        patched = self.tool.apply_native_frame_patches(blob)
        core = self.tool.member_content(
            patched, "dist/electron-main/main-core.cjs"
        ).decode("utf-8")
        renderer = self.tool.member_content(
            patched, "dist/renderer/assets/index-C57MhV1e.js"
        ).decode("utf-8")
        other = self.tool.member_content(patched, "keep/other.cjs")
        self.assertEqual(
            core,
            FULL_CORE_PATCHED,
        )
        self.assertEqual(renderer, LINUX_CONTROLS_HIDDEN)
        self.assertEqual(other, UNRELATED.encode("utf-8"))
        self.assertIn('titleBarStyle:"default"', core)
        self.assertIn("{frame:!0,titleBarStyle:\"default\"}", core)
        self.assertNotIn("{frame:!1,titleBarStyle:\"default\"}", core)
        self.assertIn("titleBarOverlay:Bx(e.backgroundColor)", core)
        self.assertNotIn("titleBarOverlay", core.split("e.isWindows?")[0])
        self.assertNotIn(
            "titleBarOverlay",
            core.split("titleBarOverlay:Bx(e.backgroundColor)}")[1],
        )
        self.assertTrue(renderer.startswith('if(c==="darwin")return null'))
        self.assertIn("if(1)return null", renderer)
        self.assertNotIn("if(o)return null;let C,T,E,R,M;if(e[15]!==r)", renderer)
        app = self.tool.member_content(
            patched, "dist/electron-main/main-app.cjs"
        ).decode("utf-8")
        self.assertEqual(app, RELAUNCH_CONTEXT_PATCHED)

    def test_menu_bar_hidden_while_native_frame_coexists(self):
        blob = sample_asar(self.tool)
        patched = self.tool.apply_native_frame_patches(blob)
        core = self.tool.member_content(
            patched, "dist/electron-main/main-core.cjs"
        ).decode("utf-8")
        # The native frame and the hidden menu bar coexist in one member.
        self.assertIn('{frame:!0,titleBarStyle:"default"}', core)
        self.assertIn("autoHideMenuBar:!0", core)
        self.assertIn(
            "new rs.BrowserWindow({...a.windowOptions,autoHideMenuBar:!0,",
            core,
        )
        self.assertIn(WINDOW_CREATE_PATCHED, core)
        self.assertIn(self.tool.MENU_HIDE_REPLACE.decode("utf-8"), core)
        self.assertEqual(core.count(self.tool.MENU_HIDE_FIND.decode("utf-8")), 1)
        # The menu itself is kept, not removed: no suppression, no overlay.
        self.assertNotIn("autoHideMenuBar:!1", core)
        self.assertNotIn("setApplicationMenu(null)", core)
        self.assertNotIn("Menu=null", core)
        self.assertNotIn("titleBarOverlay", core.split("e.isWindows?")[0])
        # Fail closed when the upstream creation shape is missing or doubled.
        full_core = FULL_CORE_UPSTREAM
        variants = {
            "missing creation site": full_core.replace(WINDOW_CREATE_UPSTREAM, ""),
            "doubled creation site": full_core.replace(
                WINDOW_CREATE_UPSTREAM,
                WINDOW_CREATE_UPSTREAM + WINDOW_CREATE_UPSTREAM,
            ),
        }
        for name, core_text in variants.items():
            with self.subTest(name):
                variant = self.tool.write_asar(
                    {
                        "dist/electron-main/main-core.cjs": core_text.encode("utf-8"),
                        "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode("utf-8"),
                    }
                )
                with self.assertRaises(self.tool.TransformError):
                    self.tool.apply_native_frame_patches(variant)

    def test_sigterm_reaches_graceful_quit_cleanup(self):
        core_text = FULL_CORE_UPSTREAM
        blob = self.tool.write_asar(
            {
                "dist/electron-main/main-core.cjs": core_text.encode("utf-8"),
                "dist/electron-main/main-app.cjs": RELAUNCH_CONTEXT_UPSTREAM.encode(
                    "utf-8"
                ),
                "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode("utf-8"),
            }
        )
        patched = self.tool.apply_native_frame_patches(blob)
        core = self.tool.member_content(
            patched, "dist/electron-main/main-core.cjs"
        ).decode("utf-8")
        # An OS SIGTERM must reach graceful app.quit (and therefore the
        # before-quit daemon cleanup) instead of killing Electron raw.
        self.assertIn('process.on("SIGTERM",()=>{he.app.quit()})', core)
        self.assertIn(self.tool.SIGTERM_QUIT_BRIDGE_REPLACE.decode("utf-8"), core)
        self.assertEqual(core.count(self.tool.SIGTERM_QUIT_BRIDGE_FIND.decode("utf-8")), 1)
        # Fail closed when the upstream bridge anchor is missing or doubled.
        for name, variant in (
            ("missing bridge anchor", core_text.replace(SIGTERM_UPSTREAM, "")),
            (
                "doubled bridge anchor",
                core_text.replace(
                    SIGTERM_UPSTREAM, SIGTERM_UPSTREAM + SIGTERM_UPSTREAM
                ),
            ),
        ):
            with self.subTest(name):
                bad = self.tool.write_asar(
                    {
                        "dist/electron-main/main-core.cjs": variant.encode("utf-8"),
                        "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode("utf-8"),
                    }
                )
                with self.assertRaises(self.tool.TransformError):
                    self.tool.apply_native_frame_patches(bad)

    def test_relaunch_uses_exit_not_hide_and_close_without_quitting_still_hides(self):
        blob = sample_asar(self.tool)
        patched = self.tool.apply_native_frame_patches(blob)
        core = self.tool.member_content(
            patched, "dist/electron-main/main-core.cjs"
        ).decode("utf-8")
        app = self.tool.member_content(
            patched, "dist/electron-main/main-app.cjs"
        ).decode("utf-8")
        # GPU restart must terminate this instance (exit), not hide.
        self.assertIn(RELAUNCH_PATCHED, app)
        self.assertNotIn(RELAUNCH_UPSTREAM, app)
        self.assertIn(self.tool.RELAUNCH_QUIT_REPLACE.decode("utf-8"), app)
        self.assertNotIn(self.tool.RELAUNCH_QUIT_FIND, patched)
        self.assertEqual(len(self.tool.RELAUNCH_QUIT_FIND), 31)
        self.assertEqual(
            len(self.tool.RELAUNCH_QUIT_FIND),
            len(self.tool.RELAUNCH_QUIT_REPLACE),
        )
        self.assertEqual(app.count("ye.app.relaunch(),ye.app.exit()"), 1)
        self.assertNotIn("ye.app.relaunch(),ye.app.quit()", app)
        # Window X without a real quit still hides.
        self.assertIn(
            's.on("close",e=>{he.app.quitting||(e.preventDefault(),s.hide())})',
            core,
        )
        self.assertIn(CLOSE_PATCHED, core)

        full_core = FULL_CORE_UPSTREAM
        variants = {
            "missing relaunch bytes": sample_asar(
                self.tool,
                extra={
                    "dist/electron-main/main-app.cjs": b"no relaunch here",
                },
            ),
            "doubled relaunch bytes": sample_asar(
                self.tool,
                extra={
                    "dist/electron-main/main-app.cjs": (
                        RELAUNCH_CONTEXT_UPSTREAM + RELAUNCH_CONTEXT_UPSTREAM
                    ).encode("utf-8"),
                },
            ),
        }
        for name, variant in variants.items():
            with self.subTest(name):
                with self.assertRaises(self.tool.TransformError):
                    self.tool.apply_native_frame_patches(variant)

        missing_close = self.tool.write_asar(
            {
                "dist/electron-main/main-core.cjs": full_core.replace(
                    CLOSE_UPSTREAM, ""
                ).encode("utf-8"),
                "dist/electron-main/main-app.cjs": RELAUNCH_CONTEXT_UPSTREAM.encode(
                    "utf-8"
                ),
                "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode(
                    "utf-8"
                ),
            }
        )
        with self.assertRaises(self.tool.TransformError):
            self.tool.apply_native_frame_patches(missing_close)

    def test_relaunch_bytes_grounded_if_asar_present(self):
        candidates = [
            os.path.join(
                REPO_ROOT, "build-dir", "files", "grok-bot", "resources", "app.asar"
            ),
            os.environ.get("GROK_BOT_APP_ASAR", ""),
        ]
        present = [path for path in candidates if path and os.path.isfile(path)]
        if not present:
            return
        find = self.tool.RELAUNCH_QUIT_FIND
        replace = self.tool.RELAUNCH_QUIT_REPLACE
        for path in present:
            with self.subTest(path=path):
                with open(path, "rb") as handle:
                    blob = handle.read()
                find_count = blob.count(find)
                replace_count = blob.count(replace)
                self.assertEqual(len(find), 31)
                # Vendor original: find once. Already-patched payload: replace
                # once. Never both, never neither, never duplicates.
                self.assertEqual(find_count + replace_count, 1, path)
                self.assertLessEqual(find_count, 1, path)
                self.assertLessEqual(replace_count, 1, path)

    def test_relaunch_vs_hide_node_probe(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for the relaunch vs hide probe")
        script = r"""
const closeWithoutQuitting = (quitting) =>
  quitting ? "destroy" : "hide";
const relaunch = process.argv[1];
const closeShape = process.argv[2];
if (closeWithoutQuitting(false) !== "hide") process.exit(2);
if (closeWithoutQuitting(true) !== "destroy") process.exit(3);
if (!relaunch.includes("ye.app.relaunch(),ye.app.exit()")) process.exit(4);
if (relaunch.includes("ye.app.relaunch(),ye.app.quit()")) process.exit(5);
if (!closeShape.includes("e.preventDefault(),s.hide()")) process.exit(6);
if (!closeShape.includes("he.app.quitting||")) process.exit(7);
process.stdout.write("relaunch=exit close=!quitting:hide\n");
"""
        proc = subprocess.run(
            [node, "-e", script, RELAUNCH_PATCHED, CLOSE_PATCHED],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "relaunch=exit close=!quitting:hide")

    def test_close_prevents_default_and_hides_while_quit_survives(self):
        blob = sample_asar(self.tool)
        patched = self.tool.apply_native_frame_patches(blob)
        core = self.tool.member_content(
            patched, "dist/electron-main/main-core.cjs"
        ).decode("utf-8")
        # 1) close prevents default and hides while not quitting.
        self.assertIn(
            's.on("close",e=>{he.app.quitting||(e.preventDefault(),s.hide())})',
            core,
        )
        self.assertIn("e.preventDefault()", core)
        self.assertIn("s.hide()", core)
        # The existing closed listener is preserved, not replaced.
        self.assertIn('s.on("closed",()=>{Ch.markRendererNotReady()})', core)
        self.assertIn(self.tool.CLOSE_INTERCEPT_REPLACE.decode("utf-8"), core)
        self.assertEqual(
            core.count(self.tool.CLOSE_INTERCEPT_FIND.decode("utf-8")), 1
        )
        # 2) explicit quit is not trapped: before-quit arms the flag and the
        # untouched window-all-closed line still quits.
        self.assertIn('he.app.once("before-quit",()=>{he.app.quitting=!0})', core)
        self.assertIn(
            'he.app.on("window-all-closed",()=>{process.platform!=="darwin"'
            '&&he.app.quit()})',
            core,
        )
        self.assertIn(self.tool.QUIT_ARM_REPLACE.decode("utf-8"), core)
        self.assertEqual(core.count(self.tool.QUIT_ARM_FIND.decode("utf-8")), 1)

    def test_close_and_quit_arm_shapes_fail_closed(self):
        full_core = FULL_CORE_UPSTREAM
        variants = {
            "missing close anchor": full_core.replace(CLOSE_UPSTREAM, ""),
            "doubled close anchor": full_core.replace(
                CLOSE_UPSTREAM, CLOSE_UPSTREAM + CLOSE_UPSTREAM
            ),
            "missing quit arm anchor": full_core.replace(ARM_UPSTREAM, ""),
            "doubled quit arm anchor": full_core.replace(
                ARM_UPSTREAM, ARM_UPSTREAM + ARM_UPSTREAM
            ),
        }
        for name, core_text in variants.items():
            with self.subTest(name):
                blob = self.tool.write_asar(
                    {
                        "dist/electron-main/main-core.cjs": core_text.encode("utf-8"),
                        "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode("utf-8"),
                    }
                )
                with self.assertRaises(self.tool.TransformError):
                    self.tool.apply_native_frame_patches(blob)

    def test_second_instance_reveals_hidden_window_not_merely_focus(self):
        blob = sample_asar(self.tool)
        patched = self.tool.apply_native_frame_patches(blob)
        core = self.tool.member_content(
            patched, "dist/electron-main/main-core.cjs"
        ).decode("utf-8")
        # Every second-instance activation reveals: focus runs before link
        # handling instead of only on the empty-argv path.
        self.assertIn(
            's=(c,l)=>{let d=Ph(r,l);t.focus();'
            'if(d.length!==0)for(let u of d)o.handleCandidate(u,"second-instance")}',
            core,
        )
        self.assertNotIn(
            'if(d.length===0){t.focus();return}'
            'for(let u of d)o.handleCandidate(u,"second-instance")',
            core,
        )
        self.assertNotIn(
            self.tool.SECOND_INSTANCE_REVEAL_FIND.decode("utf-8"), core
        )
        self.assertIn(
            self.tool.SECOND_INSTANCE_REVEAL_REPLACE.decode("utf-8"), core
        )
        # The focus target is a reveal chain, not a bare focus: a hidden
        # window is restored when minimized, shown, then focused.
        self.assertIn(FOCUS_CHAIN, core)
        self.assertIn("e.isMinimized()&&e.restore()", core)
        self.assertIn("e.show(),e.focus()", core)
        # Fail closed when the upstream activation shape is missing or doubled.
        without_activation = self.tool.write_asar(
            {
                "dist/electron-main/main-core.cjs": FULL_CORE_UPSTREAM.replace(
                    SECOND_INSTANCE_UPSTREAM, ""
                ).encode("utf-8"),
                "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode("utf-8"),
            }
        )
        with self.assertRaises(self.tool.TransformError):
            self.tool.apply_native_frame_patches(without_activation)
        doubled_activation = self.tool.write_asar(
            {
                "dist/electron-main/main-core.cjs": FULL_CORE_UPSTREAM.replace(
                    SECOND_INSTANCE_UPSTREAM,
                    SECOND_INSTANCE_UPSTREAM + SECOND_INSTANCE_UPSTREAM,
                ).encode("utf-8"),
                "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode("utf-8"),
            }
        )
        with self.assertRaises(self.tool.TransformError):
            self.tool.apply_native_frame_patches(doubled_activation)

    def test_missing_pattern_fails_closed(self):
        blob = self.tool.write_asar(
            {"dist/electron-main/main-core.cjs": LINUX_FRAMELESS.encode("utf-8")}
        )
        with self.assertRaises(self.tool.TransformError):
            self.tool.apply_native_frame_patches(blob)

    def test_ambiguous_pattern_fails_closed(self):
        blob = sample_asar(
            self.tool,
            extra={
                "dist/electron-main/main-core.cjs": (
                    FULL_CORE_UPSTREAM + LINUX_FRAMELESS
                ).encode("utf-8"),
            },
        )
        with self.assertRaises(self.tool.TransformError):
            self.tool.apply_native_frame_patches(blob)

    def test_0510_minifier_renamed_shapes_are_patched(self):
        blob = sample_modern_asar(self.tool)
        patched, applied = self.tool._apply_native_frame_rules(blob)
        self.assertFalse(
            [entry for entry in applied if entry[3]],
            "the pinned 0.51.0 fixture must use exact anchors, not fallback",
        )
        core = self.tool.member_content(
            patched, "dist/electron-main/main-core.cjs"
        )
        app = self.tool.member_content(
            patched, "dist/electron-main/main-app.cjs"
        )
        renderer = self.tool.member_content(
            patched, "dist/renderer/assets/index-B7CuLxVI.js"
        )

        self.assertIn(b'{frame:!0,titleBarStyle:"default"}', core)
        self.assertIn(b"autoHideMenuBar:!0", core)
        self.assertIn(b'e.preventDefault(),s.hide()', core)
        self.assertIn(b'he.app.once("before-quit",()=>{he.app.quitting=!0})', core)
        self.assertIn(b't.focus();if(d.length!==0)', core)
        self.assertIn(b'process.on("SIGTERM",()=>{he.app.quit()})', core)
        self.assertIn(b"if(1)return null;let C,A,E,R,N;if(e[15]!==r)", renderer)
        self.assertNotIn(b"if(o)return null;let C,A,E,R,N;if(e[15]!==r)", renderer)
        self.assertIn(b"me.app.relaunch(),me.app.exit()", app)
        self.assertNotIn(b"me.app.relaunch(),me.app.quit()", app)

        header, _json_start, _json_len, data_offset = self.tool.read_asar(patched)
        for path, meta in self.tool._walk_files(header):
            if meta.get("unpacked"):
                continue
            data = self.tool.member_content(patched, path)
            self.assertEqual(meta["size"], len(data), path)
            integrity = meta["integrity"]
            self.assertEqual(integrity["hash"], hashlib.sha256(data).hexdigest(), path)
            self.assertEqual(
                integrity["blocks"],
                [
                    hashlib.sha256(
                        data[index : index + integrity["blockSize"]]
                    ).hexdigest()
                    for index in range(0, len(data), integrity["blockSize"])
                ],
                path,
            )
        self.assertGreater(data_offset, 0)

    def test_structural_fallback_rejects_ambiguity_and_near_misses(self):
        future = sample_future_structural_asar(self.tool)
        with self.assertRaisesRegex(
            self.tool.TransformError, "structural fallback disabled"
        ):
            self.tool.apply_native_frame_patches(future)
        patched = self.tool.apply_native_frame_patches(
            future, allow_structural_fallback=True
        )
        renderer = self.tool.member_content(
            patched, "dist/renderer/assets/index-B7CuLxVI.js"
        )
        self.assertIn(b"if(1)return null", renderer)

        for decoy_path in (
            "dist/renderer/assets/index-copy.js",
            "dist/renderer/assets/index-AAAAAAAA.js",
        ):
            with self.subTest(decoy_path=decoy_path):
                ambiguous = sample_modern_asar(
                    self.tool,
                    extra={
                        "dist/renderer/assets/index-B7CuLxVI.js": b"controls moved",
                        decoy_path: MODERN_LINUX_CONTROLS.encode("utf-8"),
                    },
                )
                with self.assertRaises(self.tool.TransformError):
                    self.tool.apply_native_frame_patches(ambiguous)

        near_miss = sample_modern_asar(
            self.tool,
            extra={
                "dist/renderer/assets/index-B7CuLxVI.js": MODERN_LINUX_CONTROLS.replace(
                    "e[15]!==r", "e[14]!==r"
                ).encode("utf-8")
            },
        )
        with self.assertRaises(self.tool.TransformError):
            self.tool.apply_native_frame_patches(near_miss)

        duplicated_relaunch = sample_modern_asar(
            self.tool,
            extra={
                "dist/electron-main/main-app.cjs": (
                    MODERN_RELAUNCH_CONTEXT_UPSTREAM
                    + MODERN_RELAUNCH_CONTEXT_UPSTREAM
                ).encode("utf-8")
            },
        )
        with self.assertRaises(self.tool.TransformError):
            self.tool.apply_native_frame_patches(duplicated_relaunch)

    def test_renderer_exact_decoy_and_modern_structural_match_are_ambiguous(self):
        decoy_path = "dist/renderer/assets/unrelated.js"
        blob = sample_modern_asar(
            self.tool,
            extra={decoy_path: self.tool.IN_CONTENT_CONTROLS_FIND},
        )
        patched = self.tool.apply_native_frame_patches(blob)
        self.assertIn(
            b"if(1)return null;let C,A,E,R,N;if(e[15]!==r)",
            self.tool.member_content(
                patched, "dist/renderer/assets/index-B7CuLxVI.js"
            ),
        )
        self.assertEqual(
            self.tool.member_content(patched, decoy_path),
            self.tool.IN_CONTENT_CONTROLS_FIND,
        )

    def test_renderer_structural_decoy_is_not_the_intended_member(self):
        # A single structural-looking anchor in an unrelated asset must not
        # satisfy the controls rule when the intended index member has no
        # candidate. The old path-prefix-only rule accepted this archive.
        blob = sample_modern_asar(
            self.tool,
            extra={
                "dist/renderer/assets/index-B7CuLxVI.js": b"controls moved",
                "dist/renderer/assets/unrelated.js": MODERN_LINUX_CONTROLS.encode(
                    "utf-8"
                ),
            },
        )
        with self.assertRaises(self.tool.TransformError):
            self.tool.apply_native_frame_patches(blob)

    def test_exact_legacy_anchor_in_wrong_path_fails_closed(self):
        blob = sample_asar(
            self.tool,
            extra={
                "dist/electron-main/main-core.cjs": FULL_CORE_UPSTREAM.replace(
                    LINUX_FRAMELESS, ""
                ).encode("utf-8"),
                "keep/wrong-frame.cjs": LINUX_FRAMELESS.encode("utf-8"),
            },
        )
        with self.assertRaises(self.tool.TransformError):
            self.tool.apply_native_frame_patches(blob)

    def test_relaunch_pair_outside_target_function_fails_closed(self):
        outside_target = (
            'relaunchDesktop:()=>{let B=ne.environment.restartExitCode;return},'
            'otherTask:()=>{me.app.relaunch(),me.app.quit()}'
        )
        blob = sample_modern_asar(
            self.tool,
            extra={
                "dist/electron-main/main-app.cjs": outside_target.encode("utf-8")
            },
        )
        with self.assertRaises(self.tool.TransformError):
            self.tool.apply_native_frame_patches(blob)

    def test_cli_rewrites_asar_and_preserves_unrelated_members(self):
        blob = sample_asar(self.tool)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "app.asar")
            with open(path, "wb") as handle:
                handle.write(blob)
            self.assertEqual(self.tool.main([path]), 0)
            with open(path, "rb") as handle:
                patched = handle.read()
        self.assertNotEqual(patched, blob)
        self.assertEqual(
            self.tool.member_content(patched, "keep/other.cjs"),
            UNRELATED.encode("utf-8"),
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(self.tool.main([]), 1)
        self.assertIn("usage:", stderr.getvalue())

    def test_cli_requires_explicit_structural_fallback_and_audits_it(self):
        blob = sample_future_structural_asar(self.tool)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "app.asar")
            with open(path, "wb") as handle:
                handle.write(blob)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(self.tool.main([path]), 1)
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), blob)
            self.assertIn("--allow-structural-fallback", stderr.getvalue())
            self.assertIn("structural fallback", stderr.getvalue())

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(
                    self.tool.main(["--allow-structural-fallback", path]), 0
                )
            self.assertIn("structural fallback:", stderr.getvalue())
            with open(path, "rb") as handle:
                patched = handle.read()
        self.assertNotEqual(patched, blob)

    def test_manifest_keeps_helper_and_wrapper_forwarding(self):
        runner = load_runner_tests()
        with open(MANIFEST_PATH, encoding="utf-8") as handle:
            manifest = handle.read()
        self.assertTrue(runner.check_native_kde_frame_transform(manifest))
        self.assertFalse(
            runner.check_native_kde_frame_transform(
                manifest.replace(
                    "python3 patch_electron_native_frame.py /app/grok-bot/resources/app.asar",
                    "",
                )
            )
        )
        self.assertIn(' --password-store=basic "$@"', manifest)
        self.assertNotIn("Electron2.BaseApp", manifest)
        self.assertNotIn("--ozone-platform", manifest)

    def test_rebuild_updates_offsets_sizes_and_integrity_on_size_change(self):
        before = {
            "a/first.cjs": b"A" * 100,
            "b/mid.cjs": b"hello world, replace me!",
            "c/last.cjs": b"C" * 300,
        }
        blob = self.tool.write_asar(before, block_size=64)
        grown = b"hello world, a much longer replacement payload!"
        self.assertGreater(len(grown), len(b"replace me!"))
        out, touched = self.tool.apply_transforms(blob, [(b"replace me!", grown)], [])
        self.assertEqual(touched, {"b/mid.cjs"})
        expected_mid = before["b/mid.cjs"].replace(b"replace me!", grown)
        grown_by = len(expected_mid) - len(before["b/mid.cjs"])
        self.assertEqual(self.tool.member_content(out, "b/mid.cjs"), expected_mid)
        self.assertEqual(
            self.tool.member_content(out, "a/first.cjs"), before["a/first.cjs"]
        )
        self.assertEqual(
            self.tool.member_content(out, "c/last.cjs"), before["c/last.cjs"]
        )
        # The leading member is untouched byte for byte in the header.
        self.assertEqual(
            self.tool.member_meta(out, "a/first.cjs"),
            self.tool.member_meta(blob, "a/first.cjs"),
        )
        # The trailing member shifts by the growth while keeping size and
        # integrity bytes identical.
        meta_before = self.tool.member_meta(blob, "c/last.cjs")
        meta_after = self.tool.member_meta(out, "c/last.cjs")
        self.assertEqual(meta_after["size"], meta_before["size"])
        self.assertEqual(
            int(meta_after["offset"]), int(meta_before["offset"]) + grown_by
        )
        self.assertEqual(meta_after["integrity"], meta_before["integrity"])
        # Every member re-verifies independently against the rebuilt header.
        header, json_start, json_len, data_offset = self.tool.read_asar(out)
        cursor = data_offset
        for path, meta in self.tool._walk_files(header):
            data = self.tool.member_content(out, path)
            self.assertEqual(len(data), meta["size"], path)
            self.assertEqual(data_offset + int(meta["offset"]), cursor, path)
            integrity = meta["integrity"]
            self.assertEqual(integrity["algorithm"], "SHA256")
            self.assertEqual(
                integrity["hash"], hashlib.sha256(data).hexdigest(), path
            )
            self.assertEqual(
                integrity["blocks"],
                [
                    hashlib.sha256(data[index : index + 64]).hexdigest()
                    for index in range(0, len(data), 64)
                ],
                path,
            )
            cursor += len(data)
        self.assertEqual(cursor, len(out))

    def test_multiblock_integrity_updates_every_block(self):
        block_size = 32
        blob = self.tool.write_asar(
            {
                "dist/electron-main/main-core.cjs": FULL_CORE_UPSTREAM.encode("utf-8"),
                "dist/electron-main/main-app.cjs": RELAUNCH_CONTEXT_UPSTREAM.encode(
                    "utf-8"
                ),
                "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode("utf-8"),
            },
            block_size=block_size,
        )
        original_core = self.tool.member_meta(blob, "dist/electron-main/main-core.cjs")
        self.assertGreater(len(original_core["integrity"]["blocks"]), 1)
        patched = self.tool.apply_native_frame_patches(blob)
        for path, expected in (
            (
                "dist/electron-main/main-core.cjs",
                FULL_CORE_PATCHED.encode("utf-8"),
            ),
            ("dist/renderer/assets/index-C57MhV1e.js", LINUX_CONTROLS_HIDDEN.encode("utf-8")),
        ):
            data = self.tool.member_content(patched, path)
            integrity = self.tool.member_meta(patched, path)["integrity"]
            blocks = [
                hashlib.sha256(data[index : index + block_size]).hexdigest()
                for index in range(0, len(data), block_size)
            ]
            self.assertEqual(data, expected)
            self.assertEqual(integrity["algorithm"], "SHA256")
            self.assertEqual(integrity["blockSize"], block_size)
            self.assertEqual(integrity["hash"], hashlib.sha256(data).hexdigest())
            self.assertEqual(integrity["blocks"], blocks)
            self.assertGreater(len(blocks), 1)
            self.assertNotEqual(integrity["hash"], blocks[0])

    def test_malformed_integrity_fails_closed(self):
        path = "dist/electron-main/main-core.cjs"
        data = LINUX_FRAMELESS.encode("utf-8")
        block_size = 8
        block_count = (len(data) + block_size - 1) // block_size
        valid = {
            "algorithm": "SHA256",
            "hash": "a" * 64,
            "blockSize": block_size,
            "blocks": ["b" * 64] * block_count,
        }

        def header_for(integrity):
            entry = {"size": len(data), "offset": "0"}
            if integrity is not None:
                entry["integrity"] = integrity
            tree = {
                "files": {
                    "dist": {
                        "files": {
                            "electron-main": {
                                "files": {"main-core.cjs": entry}
                            }
                        }
                    }
                }
            }
            return json.dumps(tree, separators=(",", ":"))

        refreshed = self.tool.refresh_member_integrity(header_for(valid), path, data)
        updated = json.loads(refreshed)["files"]["dist"]["files"]["electron-main"][
            "files"
        ]["main-core.cjs"]["integrity"]
        self.assertEqual(updated["hash"], hashlib.sha256(data).hexdigest())
        self.assertEqual(
            updated["blocks"],
            [
                hashlib.sha256(data[index : index + block_size]).hexdigest()
                for index in range(0, len(data), block_size)
            ],
        )

        malformed = [
            header_for(None),
            header_for({**valid, "algorithm": "sha256"}),
            header_for({**valid, "blockSize": 0}),
            header_for({**valid, "blockSize": True}),
            header_for({**valid, "hash": "abc"}),
            header_for({**valid, "blocks": []}),
            header_for({**valid, "blocks": ["c" * 64]}),
        ]
        for json_text in malformed:
            with self.assertRaises(self.tool.TransformError):
                self.tool.refresh_member_integrity(json_text, path, data)

        blob = sample_asar(self.tool)
        missing = self.tool.write_asar(
            {
                "dist/electron-main/main-core.cjs": LINUX_FRAMELESS.encode("utf-8"),
                "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode("utf-8"),
            },
            with_integrity=False,
        )
        with self.assertRaises(self.tool.TransformError):
            self.tool.apply_native_frame_patches(missing)
        self.assertNotEqual(blob, missing)


if __name__ == "__main__":
    unittest.main()
