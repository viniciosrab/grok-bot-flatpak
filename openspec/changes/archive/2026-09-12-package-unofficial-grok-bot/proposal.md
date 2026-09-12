# Proposal: Package Unofficial Grok Bot

## Intent

Ship Unofficial Flatpak `io.github.viniciosrab.GrokBot`. Session authorization overrides `HANDOFF.md`. Link: `CONTEXT.md`, `docs/adr/0001-verify-upstream-and-adapt-payload.md`, `docs/adr/0002-publish-atomic-releases-automatically.md`, `docs/adr/0003-require-kde-tray-availability.md`.

## Scope

### In Scope
- Manifest + OSTree unpack on `org.kde.Platform`/`org.kde.Sdk` 6.11; `--socket=wayland` + `--socket=fallback-x11`; `SAND_DISABLE_UPDATES=1`
- Pin sand feed: version, URL, `commitSha`, CI SHA-256 per arch (aarch64 at pin time)
- Extract Official Grok Bot Icon from `usr/share/icons/hicolor/512x512/apps/grok-bot.png` plus hicolor set
- Qt/KF6 companion (`KStatusNotifierItem`; `--talk-name=org.kde.StatusNotifierWatcher`); show relaunches; quit both
- Dual-arch CI, atomic publish, unofficial metainfo, test runner, `HANDOFF.md` update

### Out of Scope
- Reopening ADRs 0001–0003 or CONTEXT.md glossary
- Creating icons; `resources/icon.png`; vendor hashes; extra-data; `.deb`
- Faking App/GPG/Pages/secrets; splitting PRs; enabling `strict_tdd`

## Capabilities

> Contract for sdd-spec. `openspec/specs/` has none.

### New Capabilities
- `packaged-payload`: OSTree unpack; runtime 6.11; display sockets; Electron finish-args; `SAND_DISABLE_UPDATES=1`; unofficial naming; vendor hicolor icon
- `source-checksum-pin`: sand feeds; pin version/URL/`commitSha`; CI-computed SHA-256 as Source Checksum (integrity, not vendor attestation)
- `kde-tray-companion`: separate Qt/KF6 process; SNI; show relaunches; quit both; no trayless fallback
- `atomic-flatpak-release`: dual-arch validate then one Atomic Flatpak Release; current-only Pages OSTree; pin-PR workflows as code
- `workspace-test-runner`: `python3 tools/test.py` + CTest fail-closed bootstrap

### Modified Capabilities
None

## Approach

Approach 1: CI verifies the pinned Source Checksum, unpacks AppImage into OSTree, extracts vendor hicolor, wraps companion + `SAND_DISABLE_UPDATES=1`, publishes only when both arches validate. Detect sand feeds, not `x.ai/bot`. Prove Electron sandbox on KDE 6.11 (research X3). Forecast 400-line risk; do not split.

## Affected Areas

- New: `io.github.viniciosrab.GrokBot.yml`, `companion/`, `data/`, `tools/test.py`, `tests/`, `CMakeLists.txt`, `.github/workflows/`
- Modified: `HANDOFF.md`
- Unchanged: `openspec/config.yaml` (`strict_tdd: false` until runner exists)

## Risks

- High: Electron/zypak vs KDE 6.11 (X3) — prove launch; fail closed
- Med: tray without window; Pages 1 GB — spec relaunch/quit; current-only OSTree
- High: missing App/GPG/Pages/secrets; >400-line impl — workflows as code; forecast, no split

## Rollback Plan

Revert before merge. Publish OSTree only after dual-arch validate. Bad release: republish previous current-only from tags. Never one architecture. Secrets stay out of git.

## Dependencies

Preproposal rev 4; research rev 3; sand feeds; KDE 6.11; KF6StatusNotifierItem; later human App/GPG/Pages/secrets.

## Success Criteria

- [ ] Dual-arch Packaged Payload from pinned Source Checksums; vendor icon; unofficial labeling
- [ ] Companion SNI; show relaunches; quit both; `SAND_DISABLE_UPDATES=1`
- [ ] `python3 tools/test.py` fail-closes; `strict_tdd` false; atomic workflows; provisioning human
