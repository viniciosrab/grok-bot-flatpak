# gentle-ai.sdd-research/v1

- change: package-unofficial-grok-bot
- revision: 3
- outcome: done
- accessed_at: 2026-09-12
- requested_source_classes: [open-web]
- admission: admitted
- declared_grants:
  - documentation: []
  - open-web: [webfetch]
- observed_grants:
  - documentation: []
  - open-web: [webfetch]
- observation_notes: Revision 3 is a selected-request rescope. The orchestrator withdrew question 4. Selected questions are 1–3 only. Q1–Q3 mapped claims C1–C17 were re-checked with `webfetch` on 2026-09-12 and were not contradicted. Question 4 was not fetched. AppImage/deb/rpm binaries were not downloaded. AppImage unpack, local-file SHA-256, and icon paths from other agents were not ingested. The runtime declaration admitted `open-web: [webfetch]` only. Bash, generic MCP, Context7, websearch, and persistence were not treated as evidence grants. `https://x.ai/bot` was not fetched.

## Questions

Selected:

1. Upstream feed checksum: Does any current Cursor/Grok Bot update or download endpoint return a SHA-256 for the Linux AppImage Upstream Artifact (`product sand`, stable `linux-x64` / `linux-arm64`)? If not, what evidence exists that a CI-computed SHA-256 of the downloaded AppImage can serve as the Source Checksum pin?
2. Flatpak runtime: Which `org.kde.Platform`/`org.kde.Sdk` version and which Electron/Chromium-on-Linux finish-args are documented for packaging an Electron AppImage as a Flatpak on Wayland/X11 with portals?
3. StatusNotifierItem companion: What KF6/KStatusNotifierItem (or equivalent DBus SNI) implementation stack, library, and well-known name pattern are documented for a companion tray process that stays after the app quits, can relaunch, and can quit both?

Withdrawn (not selected; no fetch; no claim):

4. Official Grok Bot Icon path. Withdrawn by orchestrator on 2026-09-12.

## Sources

### S1
- id: S1
- class: open-web
- title: Cursor Grok Bot stable download JSON (linux-x64, product sand)
- publisher: Anysphere / Cursor
- URL: https://api2.cursor.sh/updates/api/download/stable/linux-x64/sand
- accessed_at: 2026-09-12
- excerpt: `{"downloadUrl":"https://downloads.cursor.com/grokbot/stable/c1e7d7a46549956d25f53e9c0b9f59666e03aa3a/linux/x64/Grok_Bot_0.47.0.AppImage","rehUrl":"...","debUrl":"...grok-bot_0.47.0_amd64.deb","rpmUrl":"...grok-bot-0.47.0-1.x86_64.rpm","version":"0.47.0","commitSha":"c1e7d7a46549956d25f53e9c0b9f59666e03aa3a"}`

### S2
- id: S2
- class: open-web
- title: Cursor Grok Bot stable download JSON (linux-arm64, product sand)
- publisher: Anysphere / Cursor
- URL: https://api2.cursor.sh/updates/api/download/stable/linux-arm64/sand
- accessed_at: 2026-09-12
- excerpt: Same keys as S1 (`downloadUrl`, `rehUrl`, `debUrl`, `rpmUrl`, `version`, `commitSha`). ARM AppImage URL ends with `linux/arm64/Grok_Bot_0.47.0.AppImage`. Shared `commitSha` `c1e7d7a46549956d25f53e9c0b9f59666e03aa3a`. No hash field.

### S3
- id: S3
- class: open-web
- title: Download Grok Bot
- publisher: Cursor
- URL: https://cursor.com/download/bot
- accessed_at: 2026-09-12
- excerpt: Lists Linux AppImage, .deb, and RPM links for x64 and ARM64 at version 0.47.0 under `downloads.cursor.com/grokbot/stable/...`. Page text does not publish SHA-256 values.

### S4
- id: S4
- class: open-web
- title: Cursor IDE stable download JSON (linux-x64, product cursor) — field-shape comparison
- publisher: Anysphere / Cursor
- URL: https://api2.cursor.sh/updates/api/download/stable/linux-x64/cursor
- accessed_at: 2026-09-12
- excerpt: `{"downloadUrl":"...Cursor-3.20.14-x86_64.AppImage","...","version":"3.20.14","commitSha":"67ac8ff8cc118b1eddcb5f2de564c20cffcae94d"}`. Same key set as sand; no SHA-256.

### S5
- id: S5
- class: open-web
- title: Alternate sand update URL (404)
- publisher: Anysphere / Cursor
- URL: https://api2.cursor.sh/updates/api/update/linux-x64/stable/sand
- accessed_at: 2026-09-12
- excerpt: HTTP 404. Golden sand URL `https://api2.cursor.sh/updates/api/download/golden/linux-x64/sand` also HTTP 404.

### S6
- id: S6
- class: open-web
- title: Sidecar checksum URLs on downloads.cursor.com (webfetch blocked)
- publisher: Anysphere / Cursor CDN
- URL: https://downloads.cursor.com/grokbot/stable/c1e7d7a46549956d25f53e9c0b9f59666e03aa3a/linux/x64/Grok_Bot_0.47.0.AppImage.sha256
- accessed_at: 2026-09-12
- excerpt: HTTP 403 for `.AppImage.sha256` and `latest-linux.yml`. This is a retrieval failure, not proof that the objects are absent.

### S7
- id: S7
- class: open-web
- title: Flatpak module sources (sha256 required; may be calculated)
- publisher: Flatpak documentation
- URL: https://docs.flatpak.org/en/latest/module-sources.html
- accessed_at: 2026-09-12
- excerpt: "The `url` property requires a checksum to be specified after using `sha256` or `sha512`." Archive sources: "The `sha256` is the sha256 checksum of the downloaded file, supplied by upstream of the source or calculated using `sha256sum`." Extra-data: "`sha256` should be its SHA-256 checksum of the above package." File sources for squashfs/AppImage-style unpack also require `sha256` of the downloaded file.

### S8
- id: S8
- class: open-web
- title: Electron Flatpak guide
- publisher: Flatpak documentation
- URL: https://docs.flatpak.org/en/latest/electron.html
- accessed_at: 2026-09-12
- excerpt: Sample uses `runtime: org.freedesktop.Platform`, `runtime-version: '24.08'`, `base: org.electronjs.Electron2.BaseApp`. "The Freedesktop runtime is generally the best runtime to use with Electron applications". Default display: `--socket=x11` because "Electron’s Wayland support is still experimental". Native Wayland default requires `--socket=fallback-x11` and `--socket=wayland`. Launch via `zypak-wrapper`. Also `--share=ipc`, `--device=dri`, `--socket=pulseaudio`, `--share=network`, `--env=ELECTRON_TRASH=gio`, `--env=XCURSOR_PATH=/run/host/user-share/icons:/run/host/share/icons`. Unity launcher: `--talk-name=com.canonical.Unity`.

### S9
- id: S9
- class: open-web
- title: org.flathub.electron-sample-app.yml
- publisher: Flathub
- URL: https://raw.githubusercontent.com/flathub/org.flathub.electron-sample-app/master/org.flathub.electron-sample-app.yml
- accessed_at: 2026-09-12
- excerpt: `runtime-version: '25.08'`, `base: org.electronjs.Electron2.BaseApp`, `base-version: '25.08'`. finish-args: `--share=ipc`, `--socket=wayland`, `--socket=fallback-x11`, `--socket=pulseaudio`, `--share=network`, `--env=XCURSOR_PATH=...`. Wrapper: `zypak-wrapper.sh /app/main/electron-sample-app "$@"`.

### S10
- id: S10
- class: open-web
- title: Available Runtimes
- publisher: Flatpak documentation
- URL: https://docs.flatpak.org/en/latest/available-runtimes.html
- accessed_at: 2026-09-12
- excerpt: KDE runtime IDs are `org.kde.Platform` and `org.kde.Sdk`. "It is appropriate for any application that makes use of the KDE platform and most Qt-based applications." Qt6 branches are created on new Qt6 releases.

### S11
- id: S11
- class: open-web
- title: Your first Flatpak (KDE)
- publisher: KDE Developer documentation
- URL: https://develop.kde.org/docs/packaging/flatpak/packaging/
- accessed_at: 2026-09-12
- excerpt: Kate example uses `runtime: org.kde.Platform`, `runtime-version: "6.8"`, `sdk: org.kde.Sdk`, finish-args `--share=ipc`, `--socket=fallback-x11`, `--socket=wayland`. "you'll have to pick the latest available one."

### S12
- id: S12
- class: open-web
- title: Extending your package (KDE Flatpak manifest)
- publisher: KDE Developer documentation
- URL: https://develop.kde.org/docs/packaging/flatpak/manifest/
- accessed_at: 2026-09-12
- excerpt: Same `org.kde.Platform` / `6.8` / `org.kde.Sdk` example. `--socket=wayland` "allows your application to be controlled by a Wayland compositor"; `--socket=fallback-x11` "only when using an X11 session".

### S13
- id: S13
- class: open-web
- title: Qt Flatpak guide
- publisher: Flatpak documentation
- URL: https://docs.flatpak.org/en/latest/qt.html
- accessed_at: 2026-09-12
- excerpt: Example `runtime: org.kde.Platform`, `runtime-version: '5.15-24.08'`, `sdk: org.kde.Sdk`, finish-args `--share=ipc`, `--socket=fallback-x11`, `--socket=wayland`, `--device=dri`. This example is Qt5 LTS, not KF6.

### S14
- id: S14
- class: open-web
- title: Flathub appstream for org.kde.Platform
- publisher: Flathub
- URL: https://flathub.org/api/v2/appstream/org.kde.Platform
- accessed_at: 2026-09-12
- excerpt: `"bundle":{"value":"runtime/org.kde.Platform/x86_64/6.11","runtime":"org.kde.Platform/x86_64/6.11","sdk":"org.kde.Sdk/x86_64/6.11"}`. `"is_eol":false`.

### S15
- id: S15
- class: open-web
- title: org.kde.Sdk.json.in (qt6.11 branch)
- publisher: KDE (GitHub mirror of flatpak-kde-runtime)
- URL: https://raw.githubusercontent.com/KDE/flatpak-kde-runtime/qt6.11/org.kde.Sdk.json.in
- accessed_at: 2026-09-12
- excerpt: `"id": "org.kde.Sdk", "id-platform": "org.kde.Platform", "branch": "6.11", "runtime": "org.freedesktop.Platform", "sdk": "org.freedesktop.Sdk", "runtime-version": "25.08"`.

### S16
- id: S16
- class: open-web
- title: Sandbox permissions
- publisher: Flatpak documentation
- URL: https://docs.flatpak.org/en/latest/sandbox-permissions.html
- accessed_at: 2026-09-12
- excerpt: Apps that support native Wayland should use `--socket=fallback-x11` and `--socket=wayland`. Session bus is filtered; own `$FLATPAK_ID` plus portals. `/tmp` is reserved unless explicitly requested. Portals cover files, URIs, notifications.

### S17
- id: S17
- class: open-web
- title: zypak README
- publisher: refi64 / GitHub
- URL: https://github.com/refi64/zypak
- accessed_at: 2026-09-12
- excerpt: "Allows you to run Chromium based applications that require a sandbox in a Flatpak environment". Requires Freedesktop Platform/Sdk 21.08+ and `org.electronjs.Electron2.BaseApp`. Invoke `zypak-wrapper PATH/TO/MY/ELECTRON/BINARY`. Redirects Chromium sandbox to Flatpak sandbox.

### S18
- id: S18
- class: open-web
- title: Electron2.BaseApp 25.08
- publisher: Flathub
- URL: https://raw.githubusercontent.com/flathub/org.electronjs.Electron2.BaseApp/branch/25.08/org.electronjs.Electron2.BaseApp.yml
- accessed_at: 2026-09-12
- excerpt: `runtime: org.freedesktop.Platform`, `runtime-version: '25.08'`. Bundles zypak tag `v2025.09`.

### S19
- id: S19
- class: open-web
- title: Portal support in Qt and KDE
- publisher: Flatpak documentation
- URL: https://docs.flatpak.org/en/latest/portals.html
- accessed_at: 2026-09-12
- excerpt: Qt/KDE use portals inside the sandbox for `QDesktopServices::openUrl`, `QFileDialog` (avoid `DontUseNativeDialog`), and `KNotification::notify()`.

### S20
- id: S20
- class: open-web
- title: KStatusNotifierItem header
- publisher: KDE Frameworks (GitHub mirror)
- URL: https://raw.githubusercontent.com/KDE/kstatusnotifieritem/master/src/kstatusnotifieritem.h
- accessed_at: 2026-09-12
- excerpt: "This class implements the Status notifier Item D-Bus specification." "When used inside a Flatpak it is important to request explicit support in the Flatpak manifest with the following line: `--talk-name=org.kde.StatusNotifierWatcher`". Standard Quit via `quitRequested()` / `abortQuit()`. `setAssociatedWindow` since 6.0. `activate()` shows/hides the associated window.

### S21
- id: S21
- class: open-web
- title: KStatusNotifierItem implementation
- publisher: KDE Frameworks (GitHub mirror)
- URL: https://raw.githubusercontent.com/KDE/kstatusnotifieritem/master/src/kstatusnotifieritem.cpp
- accessed_at: 2026-09-12
- excerpt: `s_statusNotifierWatcherServiceName[] = "org.kde.StatusNotifierWatcher"`. Registers with `RegisterStatusNotifierItem(statusNotifierItemDBus->service())` at object path `/StatusNotifierWatcher`. Default menu includes Quit connected to `qApp->quit()` unless `abortQuit()` is called. `setStandardActionsEnabled` controls Quit.

### S22
- id: S22
- class: open-web
- title: KStatusNotifierItem D-Bus adaptor
- publisher: KDE Frameworks (GitHub mirror)
- URL: https://raw.githubusercontent.com/KDE/kstatusnotifieritem/master/src/kstatusnotifieritemdbus_p.cpp
- accessed_at: 2026-09-12
- excerpt: `m_connId(QStringLiteral("org.kde.StatusNotifierItem-%1-%2").arg(QCoreApplication::applicationPid()).arg(++s_serviceCount))`. Registers object at `/StatusNotifierItem`. `service()` returns `m_dbus.baseService()` (unique bus name). `connectToBus(SessionBus, m_connId)` uses the `org.kde.StatusNotifierItem-{pid}-{n}` string as the Qt connection name.

### S23
- id: S23
- class: open-web
- title: org.kde.StatusNotifierItem.xml / org.kde.StatusNotifierWatcher.xml
- publisher: KDE Frameworks (GitHub mirror)
- URL: https://raw.githubusercontent.com/KDE/kstatusnotifieritem/master/src/org.kde.StatusNotifierItem.xml
- accessed_at: 2026-09-12
- excerpt: Interface `org.kde.StatusNotifierItem` with Activate/ContextMenu/SecondaryActivate. Watcher interface `org.kde.StatusNotifierWatcher` method `RegisterStatusNotifierItem`.

### S24
- id: S24
- class: open-web
- title: KF6StatusNotifierItem CMake project
- publisher: KDE Frameworks (GitHub mirror)
- URL: https://raw.githubusercontent.com/KDE/kstatusnotifieritem/master/CMakeLists.txt
- accessed_at: 2026-09-12
- excerpt: `project(KStatusNotifierItem VERSION 6.31.0)`. `PACKAGE_VERSION_FILE ... KF6StatusNotifierItemConfigVersion.cmake`. `find_package(Qt6 ... REQUIRED Widgets)` and DBus on UNIX. Installs CMake package `KF6StatusNotifierItem`.

### S25
- id: S25
- class: open-web
- title: KStatusNotifierItem qdoc module use
- publisher: KDE Frameworks (GitHub mirror)
- URL: https://raw.githubusercontent.com/KDE/kstatusnotifieritem/master/src/kstatusnotifieritem-index.qdoc
- accessed_at: 2026-09-12
- excerpt: CMake module `{KF6} {StatusNotifierItem} {KF6::StatusNotifierItem}`.

## Validated claims

Each claim maps only to listed source IDs.

### Q1 — Upstream feed checksum

- C1: The current stable sand download JSON for `linux-x64` and `linux-arm64` returns `downloadUrl` (AppImage), `debUrl`, `rpmUrl`, `rehUrl`, `version` (`0.47.0`), and `commitSha` (`c1e7d7a46549956d25f53e9c0b9f59666e03aa3a`). It does not return `sha256`, `sha512`, `hash`, or `checksum`. [S1] [S2]
- C2: `https://cursor.com/download/bot` currently advertises the same 0.47.0 Linux AppImages and does not publish SHA-256 digests. [S3]
- C3: The sibling Cursor IDE download JSON uses the same field set and also omits SHA-256. [S4]
- C4: `GET .../updates/api/update/linux-x64/stable/sand` and `GET .../download/golden/linux-x64/sand` returned HTTP 404 on 2026-09-12. [S5]
- C5: Flatpak `file`/`archive`/`extra-data` sources require a SHA-256 (or SHA-512) of the downloaded bytes. Documentation states the digest may be "supplied by upstream of the source or calculated using `sha256sum`". A CI-computed SHA-256 of a downloaded AppImage is therefore a documented integrity pin for later `flatpak-builder` rebuilds of those same bytes. It is not a vendor-attested authenticity field from the sand feed. [S7]

### Q2 — Flatpak runtime and Electron finish-args

- C6: Documented KDE runtime/SDK IDs are `org.kde.Platform` and `org.kde.Sdk`. [S10] [S11]
- C7: On 2026-09-12 Flathub appstream reports the current non-EOL KDE platform bundle as `org.kde.Platform//6.11` with SDK `org.kde.Sdk//6.11`. The qt6.11 runtime recipe sets `"branch": "6.11"` on top of `org.freedesktop.Platform//25.08`. [S14] [S15]
- C8: KDE's own packaging tutorial still shows `runtime-version: "6.8"` as a worked example and tells authors to pick the latest available runtime when installing `org.kde.Sdk`. [S11] [S12]
- C9: Official Electron Flatpak documentation recommends `org.freedesktop.Platform` plus `org.electronjs.Electron2.BaseApp`, not `org.kde.Platform`, as the Electron runtime. Current sample manifest uses Freedesktop/BaseApp `25.08`. [S8] [S9] [S18]
- C10: Documented Chromium/Electron-on-Linux sandbox launch is `zypak-wrapper` (BaseApp includes zypak). [S8] [S9] [S17] [S18]
- C11: Documented Wayland/X11 finish-args for Electron: `--share=ipc`; `--device=dri` (guide); display either `--socket=x11` (guide default, Xwayland) or `--socket=wayland` plus `--socket=fallback-x11` (sample app and sandbox-permissions guideline); `--socket=pulseaudio`; `--share=network`; `--env=XCURSOR_PATH=/run/host/user-share/icons:/run/host/share/icons`. Optional `--env=ELECTRON_TRASH=gio` (guide) and `--talk-name=com.canonical.Unity` for UnityLauncherAPI badges. [S8] [S9] [S16]
- C12: Qt/KDE portal usage is documented without extra D-Bus talk names for file/URI/notification portals when using native Qt/KDE APIs. [S16] [S19]
- C13: KF6 SNI inside Flatpak requires `--talk-name=org.kde.StatusNotifierWatcher`. [S20]

### Q3 — StatusNotifierItem stack

- C14: The documented KF6 implementation is CMake package `KF6StatusNotifierItem`, link target `KF6::StatusNotifierItem`, class `KStatusNotifierItem`, depending on Qt6 Widgets and (on UNIX) Qt6 DBus plus KF6WindowSystem. Observed project version on master is 6.31.0. [S20] [S24] [S25]
- C15: Host well-known name is `org.kde.StatusNotifierWatcher` at `/StatusNotifierWatcher`, interface `org.kde.StatusNotifierWatcher`. Item interface is `org.kde.StatusNotifierItem` at object path `/StatusNotifierItem`. [S21] [S22] [S23]
- C16: KF6 constructs a Qt D-Bus connection name `org.kde.StatusNotifierItem-{pid}-{n}` and registers the item object at `/StatusNotifierItem`. `RegisterStatusNotifierItem` is called with `service()` = `QDBusConnection::baseService()` (unique name such as `:1.N`), not a request for that well-known name via `requestName`. [S21] [S22]
- C17: Documented tray interactions: `activate()` shows or hides `associatedWindow`; `hideAssociatedWindow()` forces hide; standard menu Quit emits `quitRequested()` then `qApp->quit()` unless `abortQuit()` is called. These APIs exist for a process that owns the `KStatusNotifierItem`. [S20] [S21]

## Unsupported

- None for selected questions 1–3. Question 4 is withdrawn and is not a selected research question in this revision.

## Contradictions

- X1: Electron guide [S8] still presents `--socket=x11` as the default and calls native Wayland experimental. The current sample manifest [S9] enables `--socket=wayland` and `--socket=fallback-x11` by default.
- X2: KDE tutorial [S11] uses `org.kde.Platform//6.8`. Flathub current bundle [S14] and qt6.11 recipe [S15] are `6.11` on Freedesktop `25.08`. Qt guide [S13] still shows Qt5 `5.15-24.08`.
- X3: Electron packaging docs [S8] [S9] [S17] bind Electron/zypak to `org.freedesktop.Platform` + Electron2.BaseApp. KF6 SNI docs [S20] assume a Qt/KDE stack that KDE documents on `org.kde.Platform` [S11]. No fetched source documents one Flatpak that is both an Electron BaseApp and `org.kde.Platform` simultaneously.

## Uncertainty and freshness

- All feed and Flathub observations are point-in-time 2026-09-12.
- Sidecar checksum objects on `downloads.cursor.com` returned HTTP 403 to webfetch [S6]; existence of vendor SHA-256 sidecars is unknown under this grant.
- RPM/deb feeds were not used as AppImage Source Checksum evidence (different artifacts).
- KF6 SNI is documented as an in-process tray for a Qt application. No fetched source documents a two-process "companion that stays after Electron `app.quit()`, relaunches Electron, and quits both" as a library feature. That process model remains a product/design choice on top of C14–C17.
- Combining Electron BaseApp finish-args with `org.kde.Platform//6.11` is not source-backed as a single recommended recipe (see X3).

## Product choices (non-authoritative)

Research does not confirm product decisions. The following remain pending for the orchestrator and must not be treated as evidence:

- Whether a CI-computed AppImage SHA-256 is accepted as the ADR 0001 Source Checksum when the vendor feed has no digest.
- Whether the Unofficial Flatpak uses `org.kde.Platform//6.11` (current Flathub KDE) versus `6.8` (KDE tutorial) versus `org.freedesktop.Platform//25.08` + Electron2.BaseApp (Electron docs).
- Whether Wayland is default (`fallback-x11` + `wayland`) or X11-default.
- Companion language/binary layout and D-Bus own-name under `$FLATPAK_ID`.
- Official Grok Bot Icon extraction path is outside this selected request because question 4 is withdrawn.

## Question coverage

| Question | Status |
| --- | --- |
| 1 Upstream feed checksum | answered with mapped claims C1–C5 |
| 2 Flatpak runtime / finish-args | answered with mapped claims C6–C13; runtime choice not unique |
| 3 StatusNotifierItem stack | answered with mapped claims C14–C17; two-process companion lifecycle not documented |
| 4 Official Grok Bot Icon path | withdrawn; not selected |
