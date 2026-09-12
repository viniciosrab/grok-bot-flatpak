# Design: Package Unofficial Grok Bot

## Technical Approach

Approach 1 for five specs. CI SHA-256 from Cursor sand feeds (not `x.ai/bot`), unsquash into OSTree on KDE 6.11, extract Official Grok Bot Icon plus hicolor set, wrap companion + zypak module (not `base:`). Dual-arch launch proof gates X3. ADRs 0001–0003 closed.

## Architecture Decisions

| Decision | Options | Tradeoff | Choice |
|---|---|---|---|
| Runtime vs sandbox | KDE 6.11; FDO 25.08+Electron2.BaseApp; KDE 6.8 | zypak vs KF6; X3 unproven | KDE 6.11, no `base:`, zypak module. Launch fail rejects arch |
| Source Checksum | CI SHA-256; wait vendor | Feed has no digest | CI SHA-256 per arch at pin (integrity only) |
| Install | OSTree unpack; extra-data; .deb | extra-data hits CDN; .deb ≠ ADR 0001 | unsquashfs into `/app` |
| Display | wayland+fallback-x11; x11 | X11 default | `--socket=wayland` + `--socket=fallback-x11` |
| Tray | companion; patch; trayless | Patch/trayless rejected | Qt/KF6 `KStatusNotifierItem` (ADR 0003) |

## Data Flow

```mermaid
sequenceDiagram
  participant Feed
  participant Pin
  participant Builder
  participant Companion
  participant Gate
  participant Pages
  Feed->>Pin: GET linux-x64/sand and linux-arm64/sand (not x.ai/bot)
  Pin->>Pin: version URL commitSha; sha256; mismatch/non-AppImage fail
  Pin->>Pin: App PR; missing secret fails
  Pin->>Builder: unsquashfs; install usr/share/icons/hicolor; missing 512 grok-bot.png or set/Exec reject
  Builder->>Companion: zypak + SAND_DISABLE_UPDATES=1
  Companion->>Companion: SNI then wrapper; launch fail rejects arch
  Companion->>Gate: validated payload
  Gate->>Pages: both pass: sign, current-only OSTree
  Note over Gate: one-arch fail or missing secrets: no publish
```

No Watcher → exit ≠0. Show respawns or second-exec. Quit kills child group then `qApp->quit()`. Electron `app.quit()` leaves companion up.

## File Changes

| File | Action | Description |
|---|---|---|
| `io.github.viniciosrab.GrokBot.yml` | Create | Runtime 6.11, closed finish-args, AppImage+sha256, zypak, companion, hicolor |
| `data/pins.yml` | Create | Per-arch version, sand-feed URL, commitSha, sha256 |
| `data/io.github.viniciosrab.GrokBot.desktop` | Create | Exec=companion; Icon=grok-bot |
| `data/io.github.viniciosrab.GrokBot.metainfo.xml` | Create | Unofficial AppStream |
| `companion/src/main.cpp`, `companion/CMakeLists.txt` | Create | Watcher gate, SNI, KF6 |
| `CMakeLists.txt` | Create | `bootstrap_ctest_wiring` |
| `tools/test.py` | Create | Fail-closed python + CTest |
| `tests/test_pins.py`, `tests/test_runner.py` | Create | Pin checksum; zero-test fail |
| `.github/workflows/pin.yml` | Create | Detect `linux-{x64,arm64}/sand` feeds only (not `x.ai/bot`); hash; App PR |
| `.github/workflows/validate.yml` | Create | Dual-arch build + launch proof |
| `.github/workflows/publish.yml` | Create | Atomic sign/Pages; prune current-only |
| `HANDOFF.md` | Modify | In progress |

## Interfaces / Contracts

`data/pins.yml` / `pin.yml` feed identity: only `https://api2.cursor.sh/updates/api/download/stable/linux-x64/sand` and `https://api2.cursor.sh/updates/api/download/stable/linux-arm64/sand`. Fields: `version`, `commitSha`, `architectures.{x86_64,aarch64}.{url,sha256}`. MUST NOT scrape `x.ai/bot`.

Icon extract/install: copy unpacked `usr/share/icons/hicolor/512x512/apps/grok-bot.png` and the full `usr/share/icons/hicolor/` tree to `/app/share/icons/hicolor/`. Missing 512 path or hicolor set → reject. Do not use `resources/icon.png`.

Finish-args (closed set): `--share=ipc --socket=wayland --socket=fallback-x11 --socket=pulseaudio --share=network --device=dri --talk-name=org.kde.StatusNotifierWatcher --env=SAND_DISABLE_UPDATES=1 --env=ELECTRON_TRASH=gio --env=XCURSOR_PATH=/run/host/user-share/icons:/run/host/share/icons`.

`/app/bin/grok-bot-companion`; Electron path = unpacked `Exec` (missing → reject). KF6 unique bus name only.

`python3 tools/test.py` exits 0 iff unittest and CTest ran ≥1 test and passed.

Workflows name secrets (`APP_ID`, `APP_PRIVATE_KEY`, `GPG_KEY`, Pages); never embed. Missing secret fails.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Pin schema; SHA mismatch; non-AppImage; zero tests | unittest; fail on `Ran 0 tests`; `bootstrap_ctest_wiring` |
| Integration | Watcher-missing; Show/Quit; X3 launch; 512 `grok-bot.png` + hicolor set | CTest + `validate.yml`; reject arch on fail |
| E2E | Dual-arch gate; no one-arch publish | Workflow jobs; no fake secrets |

Keep `strict_tdd: false` until runner exists.

## Threat Matrix

| Boundary | Minimum adversarial cases | Applicability | Design response | Planned RED tests |
|---|---|---|---|---|
| Documentation-like paths | `requirements.txt`, `CMakeLists.txt`, executable Markdown/MDX, `README.sh` | Applicable | Only pinned AppImage URL is executable. Unpack after sha256. | Reject non-AppImage/docs path; accept matching digest |
| Git repository selection | `git -C`, relative paths, absolute paths | Applicable | Git only in `GITHUB_WORKSPACE`; no caller `-C`. | Relative/absolute `-C` outside workspace → fail |
| Commit state | staged, `commit -a`, empty index | Applicable | Commit `data/pins.yml` by path. Never `commit -a`. Empty index → no commit. | Empty index; extra staged file; no `commit -a` |
| Push state | tracking branch, first push, explicit refspec | Applicable | Push pin branch on `origin` only. Pages from gated default branch. | Hostile refspec; missing tracking; non-origin fail |
| PR commands | explicit `--head`, environment prefix, composed commands | Applicable | `gh pr create --head` = pin branch. Feed fields never become shell. Missing App secrets fail. | Composed feed args; missing `--head`/secret |

Safe: checksum/launch fail stops that arch; one-arch fail or missing secrets stop publish. Failure: nonzero, no OSTree change.

## Migration / Rollout

No migration. Fail closed until App/GPG/Pages exist. Rollback: revert or republish prior tag. Never one architecture.

## Open Questions

- None blocking. Launch-proof fail-closed gates unproven zypak-on-KDE-6.11.
