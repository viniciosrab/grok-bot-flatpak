#!/usr/bin/env python3
"""Workspace test gate for the Unofficial Grok Bot Flatpak.

Runs every validation layer and fails closed: a missing dependency, a
failing layer, or a layer that discovers zero tests fails the whole
command. Nothing is silently skipped.

Usage:
    python3 tools/test.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(REPO_ROOT, "tests")

UNITTEST_RAN_RE = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)
CTEST_NO_TESTS_RE = re.compile(r"No tests were found", re.IGNORECASE)


def parse_unittest_summary(output: str) -> tuple[int | None, bool]:
    """Return (tests_run, overall_ok) from `unittest` output.

    `tests_run` is None when the count cannot be determined, which the
    caller must treat as a failure.
    """
    match = UNITTEST_RAN_RE.search(output or "")
    ran = int(match.group(1)) if match else None
    ok = "OK" in (output or "")
    return ran, ok


def python_layer_passes(returncode: int, output: str) -> bool:
    """Fail-closed verdict for the Python unittest layer."""
    ran, ok = parse_unittest_summary(output)
    if returncode != 0:
        return False
    if not ok:
        return False
    if ran is None or ran < 1:
        return False
    return True


def ctest_output_has_no_tests(output: str) -> bool:
    """Detect a CTest run that discovered zero tests."""
    return bool(CTEST_NO_TESTS_RE.search(output or ""))


def ctest_layer_passes(
    configure_ok: bool,
    build_ok: bool,
    test_returncode: int,
    test_output: str,
) -> bool:
    """Fail-closed verdict for the CMake/CTest layer."""
    if not configure_ok or not build_ok:
        return False
    if test_returncode != 0:
        return False
    if ctest_output_has_no_tests(test_output):
        return False
    return True


def _run(argv: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def run_python_layer() -> tuple[bool, str]:
    """Run `python -m unittest discover -s tests` and report (ok, log)."""
    if not os.path.isdir(TESTS_DIR):
        return False, f"tests directory is missing: {TESTS_DIR}"
    proc = _run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], REPO_ROOT)
    ok = python_layer_passes(proc.returncode, proc.stdout)
    return ok, proc.stdout


def run_ctest_layer() -> tuple[bool, str]:
    """Configure, build, and run CTest in a temp dir; report (ok, log)."""
    logs: list[str] = []
    for tool in ("cmake", "ctest"):
        if shutil.which(tool) is None:
            return False, f"required tool is missing from PATH: {tool}"
    with tempfile.TemporaryDirectory(prefix="grok-bot-ctest-") as build_dir:
        configure = _run(["cmake", "-S", REPO_ROOT, "-B", build_dir], REPO_ROOT)
        logs.append(configure.stdout)
        configure_ok = configure.returncode == 0
        build_ok = False
        test_rc = 1
        test_out = ""
        if configure_ok:
            build = _run(["cmake", "--build", build_dir], REPO_ROOT)
            logs.append(build.stdout)
            build_ok = build.returncode == 0
        if configure_ok and build_ok:
            test = _run(["ctest", "--output-on-failure"], build_dir)
            logs.append(test.stdout)
            test_rc = test.returncode
            test_out = test.stdout
        ok = ctest_layer_passes(configure_ok, build_ok, test_rc, test_out)
        return ok, "\n".join(logs)


def main() -> int:
    python_ok, python_log = run_python_layer()
    print("=== python layer (unittest discover -s tests) ===")
    print(python_log)
    print(f"python layer: {'PASS' if python_ok else 'FAIL'}")

    ctest_ok, ctest_log = run_ctest_layer()
    print("=== ctest layer (cmake configure/build/test) ===")
    print(ctest_log)
    print(f"ctest layer: {'PASS' if ctest_ok else 'FAIL'}")

    if python_ok and ctest_ok:
        print("workspace gate: PASS")
        return 0
    print("workspace gate: FAIL (fail-closed: no layer may be skipped)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
