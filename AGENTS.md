# Unofficial Grok Bot Flatpak — agent notes

This repo packages Cursor's Grok Bot AppImage as `io.github.viniciosrab.GrokBot` (KDE Platform/SDK 6.11, zypak module, KF6 tray companion). It is unofficial. Executable contracts live in `tests/`, the manifest, and `.github/workflows/`; do not trust stale `openspec/config.yaml` context or generic Electron BaseApp recipes.

## Quick path

1. From the repo root: `python3 tools/test.py` (needs `python3`, `cmake`, and `ctest` on PATH plus Qt6 Widgets/DBus, KF6StatusNotifierItem, KF6WindowSystem).
2. That gate is fail-closed: Python unittest discover plus CTest. Zero tests, missing tools, missing Qt6/KF6 deps, or a skipped layer fails.
3. It compiles the companion by default (`GROK_BOT_BUILD_COMPANION` defaults ON; the gate forces ON), downloads no AppImages, and proves no X3.

## Commands

| Intent | Command | Notes |
|--------|---------|--------|
| Workspace gate | `python3 tools/test.py` | Companion compiled by default (`GROK_BOT_BUILD_COMPANION` defaults ON, gate forces ON); missing Qt6/KF6 fails closed. CI runs the unchanged gate inside `org.kde.Sdk//6.11`. |
| Companion locally | `cmake -S . -B build` | Needs Qt6 Widgets/DBus, KF6StatusNotifierItem, KF6WindowSystem; ON by default. |
| Payload build | `flatpak-builder --force-clean --repo=repo build-dir io.github.viniciosrab.GrokBot.yml` | Needs Flathub `org.kde.Platform//6.11` and `org.kde.Sdk//6.11`, plus SDK ffmpeg (`/usr/bin/ffmpeg` inside `org.kde.Sdk//6.11`; never host ffmpeg). Dual-arch: `x86_64` and `aarch64`. |
| X3 proof | `bash tools/prove_x3.sh` | Repo root, `build-dir` already present. Hosted KDE: `dbus-x11`, Xvfb, `plasma-workspace` (real `plasmashell`), `kded5`, `kactivitymanagerd`, plus one D-Bus owner probe (`busctl`/`gdbus`/`dbus-send`) for GetNameOwner of `org.kde.StatusNotifierWatcher`. Expensive; not a local default. |

No repo linter, formatter, typechecker, codegen, or `scripts/` directory.

## Boundaries

| Path | Role |
|------|------|
| `io.github.viniciosrab.GrokBot.yml` | Packaged Payload. `command: grok-bot-companion`. Never `base: org.electronjs.Electron2.BaseApp`. |
| `companion/src/main.cpp` | Mandatory KF6 `KStatusNotifierItem`. Exit 1 if the watcher is missing. No trayless fallback. Owns hide/show, protocol forwarding, tracked-child graceful shutdown, and relaunched-singleton Show/Quit via Linux `SO_PEERCRED`; never kill by executable name. |
| `data/pins.yml` | Source Checksum pins. Rewritten by the pin job; do not edit by hand. |
| `data/io.github.viniciosrab.GrokBot.desktop` | `Exec=/app/bin/grok-bot-companion %u`. `MimeType=x-scheme-handler/grokbot;x-scheme-handler/sand;`. |
| `tools/test.py` | Single workspace entry. |
| `tools/source_checksum.py` | Shared consumer-verification module for both validate arch jobs: fresh non-empty retrieval + SHA-256 proof per arch. Validate consumers must reuse it; X3 keeps its separate inline checksum proof. |
| `tools/prove_x3.sh` | Shared dual-arch X3 script. |
| `tools/patch_electron_native_frame.py` | Fail-closed packed `app.asar` transform: Linux native frame, no in-content window controls, close-to-tray, hidden native menu, second-instance reveal, graceful `SIGTERM` bridge, and hardware-acceleration relaunch via `app.relaunch()` + `app.exit()`. |

Desktop `Exec` may include `%u`; CI greps `^Exec=/app/bin/grok-bot-companion( %u)?$`. Electron wrapper is `/app/bin/grok-bot-electron` (`zypak-wrapper`, `CHROME_DESKTOP=io.github.viniciosrab.GrokBot.desktop`, `--password-store=basic`). It exports absolute `SAND_DATA_ROOT=${XDG_DATA_HOME}/grok-bot` before exec (fallback `${HOME}/.local/share/grok-bot`) so vendor settings persist in private Flatpak storage and relaunch inherits the same root. Keep this in the wrapper, never as a finish-arg or host-home permission, and never restore inaccessible `${HOME}/.grokbot`.

## Companion test surface

Root `CMakeLists.txt` calls `enable_testing()` before `add_subdirectory(companion)` (enabling it later would silently drop the tests). `GROK_BOT_BUILD_COMPANION` defaults ON and the gate forces ON; missing Qt6/KF6 fails closed at configure. `companion/CMakeLists.txt` plus `companion/tests/` provide six bounded lifecycle probes (`protocol_url_filter`, `unix_socket_connect_bounded`, `unix_socket_peercred`, `owned_process_group_shutdown`, `show_quit_decision`, `cold_start_forward`) plus the `companion_watcherless_rejects_headless` negative test. Watcherless rejection is never positive X3.

## Do not

- Add `Electron2.BaseApp`, extra finish-args, or a zypak `path: nickle` overlay (nickle comes from the zypak gitlink; an overlay collides).
- Break the icon contract in `## Icons` (tray 16-on-22 canvas vs 10/11-padded taskbar/window/app-id; never opaque vendor art on app-id/window, never `find -name grok-bot.png` mass-aliasing).
- Scrape `x.ai/bot`. Pins come only from the two sand feeds in `data/pins.yml` / `pin.yml`.
- Treat validate's headless watcher step as X3. It **must** fail with exit 1 and `StatusNotifierWatcher` in the log (`QT_QPA_PLATFORM=offscreen`). Positive X3 is only `.github/workflows/x3.yml`.
- Hand-edit `data/pins.yml`. Pin commits may touch only `data/pins.yml`, `io.github.viniciosrab.GrokBot.yml`, and `data/io.github.viniciosrab.GrokBot.metainfo.xml`.
- Commit `build-dir/`, `.flatpak-builder/`, `repo/`, `.atl/`, `.codegraph/`, or `__pycache__/`. `build-dir/` and `.flatpak-builder/` are not currently protected by `.gitignore`, so check them explicitly.

Finish-args are a closed set: ipc, wayland, fallback-x11, pulseaudio, network, dri, `talk-name=org.kde.StatusNotifierWatcher`, `SAND_DISABLE_UPDATES=1`, `ELECTRON_TRASH=gio`, `XCURSOR_PATH=...`.

## Dependabot Actions

Weekly six-Action allowlist, same-major only (`.github/dependabot.yml` allow + `version-update:semver-major` ignore). The `dependabot-action-automerge` workflow runs from the trusted `pull_request_target` base and never checks out or executes PR bytes. `tools/validate_dependabot_actions.py` (fetched from the captured base OID with exact blob/byte proof) owns hostile identity, head-ref allowlist, draft, and SHA-only diff policy; the workflow keeps exact record capture/re-fetch, exact five-output enforcement (`eligible`, `pr_number`, `base_oid`, `head_oid`, `head_ref`), stale auto-merge cancellation, and commit-bound `github-actions[bot]` approval plus `--match-head-commit` merge.

## CI chain

`validate` (PR + `main` + manual) → automatic `x3` (successful **push** to `main` only; manual runs are diagnostic only) → `publish` decide gate. Ordinary pushes validate but never auto-publish. Auto-publish runs only for a genuinely new upstream `data/pins.yml` version (trusted `v*`/`flatpak/*-r*` tag provenance with semver compare, never commit messages); same-version repins no-op with success. Explicit same-version packaging republishes run only via `publish.yml` workflow_dispatch with only a required `reason` input: the run binds automatically to the exact `main` commit selected at dispatch (`github.sha`) and refuses any dispatch not from `refs/heads/main`. That snapshot must be an exact 40-char commit existing as an ancestor of `origin/main` (it need not still be the tip; a later `main` push may race) already carrying successful validate and dual-arch X3 for that exact SHA, plus required `reason`. PR/manual diagnostic runs never publish without that explicit dispatch. Every publish job checks out the decided SHA, not implicit default-branch bytes.

Publish merges both arch OSTree repos, recreates empty `refs/remotes` (GitHub artifacts drop them). The private `GPG_KEY` stays release-job-only: every distinct OSTree ref commit is signed, the public key is exported as `site/grok-bot.gpg` and `site/grok-bot.flatpakrepo` (clients add that descriptor; never `--no-gpg-verify`), and every ref is consumer-verified with only that key before packaging. Keeps internal `flatpak/${VERSION}-rN` build tags plus deployed markers (new backups as hidden draft releases, never public/never Latest; legacy public backups untouched), and creates-or-updates the public release `v${VERSION}` titled exactly `Grok Bot v${VERSION}` (same-version updates upload `--clobber`, never a new public entry), then deploys Pages. Manual publish: Actions → publish → Run workflow with the branch selector on `main` and only `reason` entered (CLI: `gh workflow run publish.yml --ref main -f reason="..."`). `site.tar.gz` on GitHub Releases is audit/rollback, not an installer. First-release rollback is a no-op. Pin job secrets: `APP_ID`, `APP_PRIVATE_KEY`.

## Protocol and lock

`grokbot:` and `sand:` URLs must reach Electron. A second companion instance that loses `grok-bot-companion.lock` still forwards those URLs and exits 0. Cold-start delivery waits for Electron's singleton socket before forwarding. A hardware-acceleration relaunch leaves the new Electron outside the companion's tracked `QProcess`; Show must second-exec that live singleton, and tray Quit must identify it through the socket peer credentials, request graceful shutdown, and retain bounded fallback behavior.

## Icons (canonical)

Tray: preserved `/app/grok-bot/resources/icon.upstream.png` (rounded vendor `resources/icon.png` saved before any replacement), scaled 16x16 on a transparent 22x22 QPainter canvas via `setIconByPixmap(QIcon(trayCanvas))`. Never route the tray through hicolor copies, and never apply the tray canvas to the taskbar.

Taskbar/window/app-id: same rounded source with 10/11 inner artwork on a transparent canvas (~91%, KDE-like 20/22 padding). Scale with SDK ffmpeg `inner=$((size*10/11)); scale=${inner}:${inner}:flags=lanczos,pad=${size}:${size}:(ow-iw)/2:(oh-ih)/2:color=0x00000000`, bitexact; require SDK ffmpeg. Never 8/11 padding, never unpadded full-canvas, never opaque vendor `grok-bot.png` on these surfaces, never export app-id hicolor at 1024 (`flatpak-builder` max is 512). After the app-id hicolor names (`16 24 32 48 64 128 256 512`) exist, overwrite vendor-named `grok-bot.png` at each exported hicolor size (and under `/app/grok-bot/usr/share/icons/hicolor` when present) with the same padded bytes, because `StartupWMClass=grok-bot` makes Plasma look up those names. After preserve, ffmpeg padded 1024 (`inner=$((1024*10/11))`, `pad=1024:1024`) into `/app/grok-bot/resources/icon.png` and `/app/grok-bot/grok-bot.png`.
