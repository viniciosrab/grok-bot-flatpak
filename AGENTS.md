# Unofficial Grok Bot Flatpak — agent notes

This repo packages Cursor's Grok Bot AppImage as `io.github.viniciosrab.GrokBot` (KDE Platform/SDK 6.11, zypak module, KF6 tray companion). It is unofficial. Executable contracts live in `tests/`, the manifest, and `.github/workflows/`; do not trust stale `openspec/config.yaml` context, README links to missing `CONTEXT.md`/`docs/adr/`, or generic Electron BaseApp recipes.

## Quick path

1. From the repo root: `python3 tools/test.py` (needs `python3`, `cmake`, and `ctest` on PATH).
2. That gate is fail-closed: Python unittest discover plus CTest. Zero tests, missing tools, or a skipped layer fails.
3. It does **not** compile the companion, download AppImages, or prove X3.

## Commands

| Intent | Command | Notes |
|--------|---------|--------|
| Workspace gate | `python3 tools/test.py` | Companion stays off (`GROK_BOT_BUILD_COMPANION` defaults OFF). |
| Companion locally | `cmake -S . -B build -DGROK_BOT_BUILD_COMPANION=ON` | Needs Qt6 Widgets/DBus, KF6StatusNotifierItem, KF6WindowSystem. Not required for the gate. |
| Payload build | `flatpak-builder --force-clean --repo=repo build-dir io.github.viniciosrab.GrokBot.yml` | Needs Flathub `org.kde.Platform//6.11` and `org.kde.Sdk//6.11`. Dual-arch: `x86_64` and `aarch64`. |
| X3 proof | `bash tools/prove_x3.sh` | Repo root, `build-dir` already present. Hosted KDE: Xvfb, real `plasmashell`, `kactivitymanagerd`, GetNameOwner of `org.kde.StatusNotifierWatcher`. Expensive; not a local default. |

No repo linter, formatter, typechecker, or codegen. `scripts/` is empty.

## Boundaries

| Path | Role |
|------|------|
| `io.github.viniciosrab.GrokBot.yml` | Packaged Payload. `command: grok-bot-companion`. Never `base: org.electronjs.Electron2.BaseApp`. |
| `companion/src/main.cpp` | Mandatory KF6 `KStatusNotifierItem`. Exit 1 if the watcher is missing. No trayless fallback. |
| `data/pins.yml` | Source Checksum pins. Rewritten by the pin job; do not edit by hand. |
| `data/io.github.viniciosrab.GrokBot.desktop` | `Exec=/app/bin/grok-bot-companion %u`. `MimeType=x-scheme-handler/grokbot;x-scheme-handler/sand;`. |
| `tools/test.py` | Single workspace entry. |
| `tools/prove_x3.sh` | Shared dual-arch X3 script. |
| `tools/patch_electron_native_frame.py` | Fail-closed packed `app.asar` transform: Linux native frame (`frame: true`, default `titleBarStyle`, no `titleBarOverlay`) and no in-content min/max/close widget. |

Desktop `Exec` may include `%u`; CI greps `^Exec=/app/bin/grok-bot-companion( %u)?$`. Electron wrapper is `/app/bin/grok-bot-electron` (`zypak-wrapper`, `CHROME_DESKTOP=io.github.viniciosrab.GrokBot.desktop`, `--password-store=basic`).

## Do not

- Add `Electron2.BaseApp`, extra finish-args, or a zypak `path: nickle` overlay (nickle comes from the zypak gitlink; an overlay collides).
- Export app-id hicolor at 1024 (`flatpak-builder` max is 512). Apply the tray 16-on-22 canvas to taskbar/window icons, add 8/11 padding, or install unpadded full-canvas artwork on those surfaces.
- Use `find -name grok-bot.png` to mass-alias icons. Do not copy opaque vendor hicolor `grok-bot.png` onto app-id or window paths. Preserve rounded vendor `resources/icon.png` as `/app/grok-bot/resources/icon.upstream.png` before replacing the Electron resource. Scale that same rounded source to app-id hicolor names (`16 24 32 48 64 128 256 512`) with SDK ffmpeg `inner=$((size*10/11)); scale=${inner}:${inner}:flags=lanczos,pad=${size}:${size}:(ow-iw)/2:(oh-ih)/2:color=0x00000000`, bitexact. Require ffmpeg. After those app-id icons exist, overwrite vendor-named `grok-bot.png` in exported hicolor and in `/app/grok-bot/usr/share/icons/hicolor` when present with those same padded bytes. After preserve, ffmpeg padded 1024 (`inner=$((1024*10/11))`, `pad=1024:1024`) into `/app/grok-bot/resources/icon.png` and `/app/grok-bot/grok-bot.png`. Do not feed opaque vendor art to taskbar/window/app-id.
- Change the tray icon. Tray already uses preserved `icon.upstream.png`, scaled 16x16 on a transparent 22x22 QPainter canvas via `setIconByPixmap(QIcon(trayCanvas))`. Do not route the tray through hicolor copies.
- Scrape `x.ai/bot`. Pins come only from the two sand feeds in `data/pins.yml` / `pin.yml`.
- Treat validate's headless watcher step as X3. It **must** fail with exit 1 and `StatusNotifierWatcher` in the log (`QT_QPA_PLATFORM=offscreen`). Positive X3 is only `.github/workflows/x3.yml`.
- Hand-edit `data/pins.yml`. Pin commits may touch only `data/pins.yml`, `io.github.viniciosrab.GrokBot.yml`, and `data/io.github.viniciosrab.GrokBot.metainfo.xml`.
- Commit `build-dir/`, `repo/`, `.atl/`, `.codegraph/`, or `__pycache__/`.

Finish-args are a closed set: ipc, wayland, fallback-x11, pulseaudio, network, dri, `talk-name=org.kde.StatusNotifierWatcher`, `SAND_DISABLE_UPDATES=1`, `ELECTRON_TRASH=gio`, `XCURSOR_PATH=...`.

## CI chain

`validate` (PR + `main`) → automatic `x3` (successful **push** to `main` only) → `publish`. Manual/PR never publish. X3/publish check out the triggering head SHA, not implicit default-branch bytes.

Publish merges both arch OSTree repos, recreates empty `refs/remotes` (GitHub artifacts drop them), signs with `GPG_KEY`, tags `flatpak/${VERSION}-rN`, deploys Pages. `site.tar.gz` on GitHub Releases is audit/rollback, not an installer. First-release rollback is a no-op. Pin job secrets: `APP_ID`, `APP_PRIVATE_KEY`.

## Protocol and lock

`grokbot:` and `sand:` URLs must reach Electron. A second companion instance that loses `grok-bot-companion.lock` still forwards those URLs and exits 0.

Taskbar/window icon: vendor `resources/icon.png` (rounded-edge artwork used by the tray) with 10/11 inner artwork on a transparent canvas (~91%, KDE-like 20/22 padding). Scale that source to app-id hicolor (`16 24 32 48 64 128 256 512`) with SDK ffmpeg `inner=$((size*10/11)); scale=${inner}:${inner}:flags=lanczos,pad=${size}:${size}:(ow-iw)/2:(oh-ih)/2:color=0x00000000`; require ffmpeg; not 8/11 and not unpadded full-canvas. After those app-id icons exist, overwrite vendor-named `grok-bot.png` at each exported hicolor size (and under `/app/grok-bot/usr/share/icons/hicolor` when present) with the same padded bytes, because `StartupWMClass=grok-bot` makes Plasma look up those names. After preserve, ffmpeg padded 1024 (`inner=$((1024*10/11))`, `pad=1024:1024`) into `/app/grok-bot/resources/icon.png` and `/app/grok-bot/grok-bot.png`. Tray icon: preserved `/app/grok-bot/resources/icon.upstream.png` with the established 16-on-22 canvas. Do not apply the tray canvas to the taskbar, and do not send opaque vendor hicolor `grok-bot.png` to taskbar/window/app-id.
