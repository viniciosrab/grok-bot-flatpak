# Tasks: Package Unofficial Grok Bot

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 700–950 authored lines across 15 files |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Single PR only after `size:exception`; organize commits by work unit |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Runner, CTest wiring, pins, and pin safety | PR 1 after exception | `python3 tools/test.py` | `python3 tools/test.py` from clean checkout | `CMakeLists.txt`, `tools/test.py`, `tests/`, `data/pins.yml`, `pin.yml` |
| 2 | Payload and mandatory KDE companion | PR 1 after exception | `python3 tools/test.py` | `flatpak run io.github.viniciosrab.GrokBot` in KDE session | Manifest, `companion/`, and `data/` payload files |
| 3 | Atomic CI publication and handoff | PR 1 after exception | `python3 tools/test.py` | N/A: requires configured GitHub/App/GPG/Pages secrets | `.github/workflows/` and `HANDOFF.md` |

## Phase 1: Test Foundation and RED Contracts

- [x] 1.1 Create `CMakeLists.txt`, `tools/test.py`, and `tests/test_runner.py`; bootstrap CTest, require at least one test, fail closed on setup/test errors, and keep `strict_tdd` disabled.
- [x] 1.2 RED: extend `tests/test_pins.py` to reject documentation-like/non-AppImage paths and changed SHA-256 bytes while accepting a matching digest.
- [x] 1.3 RED: extend `tests/test_pins.py` to reject relative/absolute `git -C` outside `GITHUB_WORKSPACE`, empty index/extra staged files, `commit -a`, hostile refspecs, missing tracking, non-origin pushes, composed feed arguments, missing `--head`, and missing secrets.

## Phase 2: Pinning, Payload, and Companion

- [x] 2.1 Implement `data/pins.yml` and `.github/workflows/pin.yml` for only the two sand feeds, version/URL/`commitSha`/per-architecture SHA-256, path-only pin commits, explicit pin branch PRs, and fail-closed secrets.
- [x] 2.2 RED: add CTest/unittest checks in `tests/test_runner.py` for missing StatusNotifierWatcher, missing vendor 512 icon/hicolor tree, missing Electron `Exec`, and failed KDE/Electron launch; each must reject the architecture without OSTree change.
- [x] 2.3 Implement `companion/src/main.cpp` and `companion/CMakeLists.txt` with unique KF6 bus identity, watcher gate, SNI Show relaunch/reveal, and Quit child-group termination plus `qApp->quit()`.
- [x] 2.4 Implement `io.github.viniciosrab.GrokBot.yml`, `data/io.github.viniciosrab.GrokBot.desktop`, and `data/io.github.viniciosrab.GrokBot.metainfo.xml` with KDE/SDK 6.11, zypak, closed finish-args, companion Exec, unofficial labels, and vendor hicolor extraction.

## Phase 3: Validation and Atomic Release

- [x] 3.1 RED: add checks in `tests/test_runner.py` proving both architectures are required and a source/payload/runtime failure publishes neither release nor new OSTree.
- [x] 3.2 Implement `.github/workflows/validate.yml` for dual-architecture build, icon/Exec checks, KDE tray checks, and X3 launch proof; fail the affected architecture on any failure.
- [x] 3.3 Implement `.github/workflows/publish.yml` to gate signing and Pages publication on all validation jobs, retain only current OSTree content, require named secrets, and recover from tagged content.

## Phase 4: Verification and Handoff

- [x] 4.1 Update `HANDOFF.md` with implementation-in-progress status, human provisioning requirements, and the no-partial-release rollback boundary.
- [x] 4.2 Run `python3 tools/test.py` and review workflow/manifest assertions against all five specs; record failures rather than weakening fail-closed behavior.
