"""Fail-closed packed app.asar transform: native KDE frame, close-to-hide
lifecycle, second-instance reveal, and hidden menu bar."""

import hashlib
import importlib.util
import io
import json
import os
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
        "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode("utf-8"),
        "keep/other.cjs": UNRELATED.encode("utf-8"),
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
                "dist/copy/main-core.cjs": LINUX_FRAMELESS.encode("utf-8"),
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
