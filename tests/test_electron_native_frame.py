"""Native KDE frame transform: disable Electron in-content window controls."""

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
UNRELATED = 'other:{frame:!1,titleBarStyle:"hidden"} keep me'


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
        "dist/electron-main/main-core.cjs": LINUX_FRAMELESS.encode("utf-8"),
        "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode("utf-8"),
        "keep/other.cjs": UNRELATED.encode("utf-8"),
    }
    if extra:
        files.update(extra)
    return tool.write_asar(files)


class NativeFrameTransformTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()

    def test_patches_are_same_length_and_distinct(self):
        for find, replace in self.tool.PATCHES:
            self.assertEqual(len(find), len(replace), find)
            self.assertNotEqual(find, replace)

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
        self.assertEqual(core, LINUX_NATIVE)
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

    def test_multiblock_integrity_updates_every_block(self):
        block_size = 32
        blob = self.tool.write_asar(
            {
                "dist/electron-main/main-core.cjs": LINUX_FRAMELESS.encode("utf-8"),
                "dist/renderer/assets/index-C57MhV1e.js": LINUX_CONTROLS.encode("utf-8"),
            },
            block_size=block_size,
        )
        original_core = self.tool.member_meta(blob, "dist/electron-main/main-core.cjs")
        self.assertGreater(len(original_core["integrity"]["blocks"]), 1)
        patched = self.tool.apply_native_frame_patches(blob)
        for path, expected in (
            ("dist/electron-main/main-core.cjs", LINUX_NATIVE.encode("utf-8")),
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
