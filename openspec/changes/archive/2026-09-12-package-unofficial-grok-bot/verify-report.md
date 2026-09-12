```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:ef878529eea7e821b8150e25568f575c2740dde82628d4b0a9c20738a8df7db7
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 5/5
scenarios: 10/10
test_command: python3 tools/test.py
test_exit_code: 0
test_output_hash: sha256:198271b6a58f1552dfe8542f4eb0b86a710ad4d7c54e369079758d9bdfabdae9
build_command: cmake -S . -B /tmp/opencode/sdd-verify-build && cmake --build /tmp/opencode/sdd-verify-build
build_exit_code: 0
build_output_hash: sha256:6b3b1f68f644c4d22deccd4f1a44b05b8b2aeb7a31cd7c4f77ca6a675e7f3ef3
```

## Verification Report

**Change**: package-unofficial-grok-bot
**Version**: N/A
**Mode**: Standard

This report supersedes prior evidence_revision `sha256:1742e623a9ab4d3e6fca6d798f822988b37752265135c5fcd65094b4f3ec7fd6` (archived verify of 55 unittest). Current live HEAD is `63de6496b4f67f614fe363a3434c63f00cf7d395` on `feat/package-unofficial-grok-bot`. Native status reports the change archived; this re-verify covers the post-archive review-fix delta against the live worktree.

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 12 |
| Tasks complete | 12 |
| Tasks incomplete | 0 |

All tasks 1.1–4.2 are marked `[x]` in `openspec/changes/archive/2026-09-12-package-unofficial-grok-bot/tasks.md`. Canonical specs in `openspec/specs/` match the archived delta specs (5 requirements, 10 scenarios).

### Build & Tests Execution
**Build**: ✅ Passed
```text
cmake -S . -B /tmp/opencode/sdd-verify-build && cmake --build /tmp/opencode/sdd-verify-build
exit 0
-- Configuring done (0.0s)
-- Generating done (0.0s)
-- Build files have been written to: /tmp/opencode/sdd-verify-build
```

**Tests**: ✅ 61 unittest passed + CTest 1/1 passed / ❌ 0 failed / ⚠️ 0 skipped
```text
python3 tools/test.py
exit 0
=== python layer (unittest discover -s tests) ===
Ran 61 tests in 0.008s
OK
python layer: PASS
=== ctest layer (cmake configure/build/test) ===
1/1 Test #1: bootstrap_ctest_wiring ...........   Passed    0.00 sec
100% tests passed out of 1
ctest layer: PASS
workspace gate: PASS
```

**Coverage**: ➖ Not available / threshold: 0% → ➖ Not available

### Spec Compliance Matrix
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Build the unofficial payload | Valid payload is assembled | `tests/test_runner.py > test_payload_checks_accept`, `test_payload_files_exist`, `test_metainfo_marks_unofficial`, `test_manifest_sources_match_pins` | ✅ COMPLIANT |
| Build the unofficial payload | Required payload evidence is absent | `tests/test_runner.py > test_single_failed_check_rejects_without_ostree_change`, `test_redesigned_icon_path_rejects`, `test_base_app_base_rejects` | ✅ COMPLIANT |
| Pin and verify source artifacts | Pinned source is accepted | `tests/test_pins.py > test_matching_digest_accepted`, `test_appimage_url_accepted`, `test_artifact_host_requires_exact_hostname`, `test_pins_file_exists_and_validates`, `test_pins_feeds_are_only_sand_feeds` | ✅ COMPLIANT |
| Pin and verify source artifacts | Pinned bytes change | `tests/test_pins.py > test_changed_bytes_rejected`, `test_malformed_digests_rejected`, `test_documentation_like_paths_rejected`, `test_pins_schema_rejects_docs_paths_and_changed_bytes`; `tests/test_runner.py > test_validate_fails_arch_on_source_failure` | ✅ COMPLIANT |
| Provide a mandatory tray companion | Tray actions control the application | `tests/test_runner.py > test_payload_checks_accept` (KStatusNotifierItem, Show second-exec/relaunch, Quit `killpg`/`qApp->quit()`) | ✅ COMPLIANT |
| Provide a mandatory tray companion | Tray availability is missing | `tests/test_runner.py > test_payload_checks_accept`, `test_validate_runs_workspace_gate_and_payload_proof`; companion `watcherAvailable()` returns 1 | ✅ COMPLIANT |
| Publish only validated atomic releases | Both architectures pass | `tests/test_runner.py > test_both_arches_required`, `test_validate_covers_both_arches`, `test_publish_gates_on_all_validation`, `test_publish_has_concurrency_group` | ✅ COMPLIANT |
| Publish only validated atomic releases | One architecture fails | `tests/test_runner.py > test_failed_gate_publishes_nothing`, `test_source_payload_runtime_failure_blocks_arch`, `test_publish_rollback_uses_newest_deployed_tag`, `test_publish_tag_step_uses_revisioned_tags` | ✅ COMPLIANT |
| Run workspace validation through one entry point | Tests pass from a clean workspace | Live `python3 tools/test.py` exit 0 (61 unittest + CTest 1/1); `tests/test_runner.py > test_runner_module_exists`, `test_passing_python_suite_requires_ok_and_count` | ✅ COMPLIANT |
| Run workspace validation through one entry point | Bootstrap or test fails | `tests/test_runner.py > test_zero_python_tests_fail_closed`, `test_unparseable_python_output_fails_closed`, `test_failing_python_suite_fails_closed`, `test_ctest_no_tests_found_fails_closed`, `test_ctest_layer_requires_every_step` | ✅ COMPLIANT |

**Compliance summary**: 10/10 scenarios compliant

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| Build the unofficial payload | ✅ Implemented | `io.github.viniciosrab.GrokBot.yml` uses KDE Platform/SDK 6.11, closed finish-args including wayland+fallback-x11 and `SAND_DISABLE_UPDATES=1`, zypak `simple`+`make` at pinned commit with vendored nickle (no Electron2.BaseApp), `--appimage-extract` plus vendor 512 `grok-bot.png` and hicolor tree, unofficial desktop/metainfo. |
| Pin and verify source artifacts | ✅ Implemented | `data/pins.yml` pins version/commitSha/sand feeds/SHA-256 per arch. `pin.yml` queries only the two sand feeds, requires exact `downloads.cursor.com` hostname, hashes both AppImages, writes pins **and** matching manifest url/sha256 **and** metainfo release, idle-skips via `changed=false`, refreshes existing pin branch with extraheader `--force-with-lease` push. |
| Provide a mandatory tray companion | ✅ Implemented | KF6 `KStatusNotifierItem`; watcher gate exit 1; Show relaunches via second-exec or `startChild`; Quit requires `pgid==pid` and `pgid != own group` before `killpg`, then `qApp->quit()`. Single-instance lock plus child error reporting. No trayless fallback. |
| Publish only validated atomic releases | ✅ Implemented | `validate.yml` dual-arch native builds with `sudo flatpak` system ops, checksum, icon/Exec, negative watcher gate, X3 `prove_x3` bus proof + stay-alive fail-closed. `publish.yml` gates on `workflow_run` success **and** `event==push`; `concurrency.group: publish` with `cancel-in-progress: false`; revisioned `flatpak/${VERSION}-rN` tags; deployed-bit markers; rollback recovers newest `flatpak/deployed-*-r*`. |
| Run workspace validation through one entry point | ✅ Implemented | `tools/test.py` fail-closes on missing tools, zero tests, or any layer failure. Live gate: 61 unittest + CTest 1/1. `strict_tdd` remains false. |

Live worktree confirmed (outranks stale apply-progress snapshots and the prior 55-test evidence revision):
1. Pin job writes `data/pins.yml`, `io.github.viniciosrab.GrokBot.yml`, and `data/io.github.viniciosrab.GrokBot.metainfo.xml`; idle skip `changed=false`; existing pin branch refreshed with `git checkout -B` and extraheader push.
2. Publish `if` requires success and `event==push`; revisioned tags precede Pages; deployed marker `flatpak/deployed-${VERSION}-r${RELEASE_R}`; rollback `needs: [release]` with `failure() && needs.release.result == 'failure'`; newest deployed tag, not `grep -Fxv`.
3. `prove_x3` requires busctl/gdbus/dbus-send listing `org.kde.StatusNotifierWatcher` plus companion stay-alive.
4. Companion `killpg` gated on `pgid == pid && pgid != getpgrp()`; `QLockFile` single-instance; child `errorOccurred` warnings.
5. `test_publish_rollback_uses_newest_deployed_tag`, `test_publish_tag_step_uses_revisioned_tags`, `test_workflows_use_sudo_for_flatpak_system_ops`, and `test_artifact_host_requires_exact_hostname` exist and passed.

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| KDE 6.11, no `base:`, zypak module; launch fail rejects arch | ✅ Yes | Manifest zypak simple+make + nickle; validate X3 fail-closed |
| CI SHA-256 Source Checksum per arch at pin time | ✅ Yes | pin.yml sha256sum; integrity only |
| unsquashfs into `/app`; reject missing 512 icon/hicolor/Exec | ⚠️ Partial | Live unpack is `./Grok_Bot_*.AppImage --appimage-extract` then copy into `/app`; missing 512/hicolor/Exec still reject. Spec-compliant unpack; design verb is stale |
| `--socket=wayland` + `--socket=fallback-x11` | ✅ Yes | closed finish-args match design set |
| Qt/KF6 `KStatusNotifierItem`; no trayless fallback | ✅ Yes | companion + talk-name |
| Sand feeds only; never scrape `x.ai/bot` | ✅ Yes | pin.yml + pins.yml tests |
| Dual-arch gate; missing secrets fail; recover from tags | ✅ Yes | publish.yml concurrency + deployed-bit rollback |
| Commit pins by path; never `commit -a` | ⚠️ Partial | Pin commit is path-only but includes pins, manifest, and metainfo (corrected contract; tests allow all three) |
| CTest covers watcher/Show/Quit/X3 | ⚠️ Partial | Workspace CTest is bootstrap-only; companion/X3 proofs live in unittest contracts + `validate.yml` |
| Desktop `Icon=grok-bot` | ⚠️ Partial | Desktop uses `Icon=io.github.viniciosrab.GrokBot`; manifest copies vendor 512 PNG to that name. Spec-compliant vendor icon; design filename is stale |

### Issues Found
**CRITICAL**: None

**WARNING**:
1. X3 graphical Electron/zypak launch remains unproven on GitHub-hosted runners. `prove_x3` fail-closes without a live `StatusNotifierWatcher` on the session bus. This matches the design fail-closed gate and HANDOFF; it is not a silent pass. First publication still needs a graphical KDE runner.
2. `HANDOFF.md` still says the runner passes 58 unittest checks; live evidence is 61.
3. `openspec/config.yaml` context block still claims `tools/test.py` and CTest layers are not present on disk, even though `testing.capabilities` and the live gate contradict that.
4. Workspace CMake keeps `GROK_BOT_BUILD_COMPANION` OFF, so the local build/test gate does not compile the KF6 companion. Companion compilation is the Flatpak/CI path.
5. Design file-changes originally described unsquashfs, `Icon=grok-bot`, and committing only `data/pins.yml`. Live code uses `--appimage-extract`, the app-id icon name, and path-only commits of pins+manifest+metainfo. Spec-compliant; design table is stale.

**SUGGESTION**:
1. Add a unittest that asserts `prove_x3` requires a D-Bus probe (`busctl`/`gdbus`/`dbus-send`) rather than only the generic `launch` substring.
2. Remove unused `find_package(KF6WindowSystem)` from `companion/CMakeLists.txt`.
3. Refresh `HANDOFF.md` unittest count (58 → 61) and the stale `openspec/config.yaml` context sentence.
4. Provision GitHub App, GPG, Pages, and a graphical KDE runner before unattended publish.

### Verdict
PASS WITH WARNINGS
All 5 requirements and 10 scenarios have passing covering tests on HEAD `63de649`; remaining items are documented follow-ups, not fail-closed regressions. This revision supersedes `sha256:1742e623a9ab4d3e6fca6d798f822988b37752265135c5fcd65094b4f3ec7fd6`.
