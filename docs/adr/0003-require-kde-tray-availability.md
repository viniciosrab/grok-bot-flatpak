# Require KDE tray availability

The Unofficial Flatpak will provide a companion StatusNotifierItem and require its successful registration before starting Grok Bot. Inspection of the verified Grok Bot 0.47.0 `x86_64` and `aarch64` Upstream Artifacts found no Electron `Tray` construction or StatusNotifierItem integration; on Linux, closing the last window instead calls `app.quit()`.

The companion will remain available after Grok Bot exits, expose explicit show and quit actions, and relaunch Grok Bot when show is selected while it is not running. Absence of `StatusNotifierWatcher` will produce a clear startup failure. Patching the minified upstream Electron application to implement close-to-hide was rejected as brittle, and a degraded trayless mode was rejected because KDE tray integration is a non-negotiable product requirement.
