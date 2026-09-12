                                                                                        ## Exploration: package-unofficial-grok-bot

### Current State

The repository is documentation-first. Canonical language lives in `CONTEXT.md`. Provenance, atomic publishing, and KDE tray contracts are already recorded in ADRs 0001–0003. `HANDOFF.md` still says implementation is deferred; session authorization now overrides that wait. OpenSpec is initialized (`openspec/config.yaml`) with `strict_tdd: false` and no live workspace test runner. CodeGraph indexes docs only; there is no Flatpak manifest, companion, workflow, signing config, or `tools/test.py`.

Re-queried 2026-09-12 (do not scrape `https://x.ai/bot`):

| Arch | Feed | Version | Artifact | Bytes | Last-Modified |
| --- | --- | --- | --- | --- | --- |
| x86_64 | `GET https://api2.cursor.sh/updates/api/download/stable/linux-x64/sand` | 0.47.0 | `https://downloads.cursor.com/grokbot/stable/c1e7d7a46549956d25f53e9c0b9f59666e03aa3a/linux/x64/Grok_Bot_0.47.0.AppImage` | 132115801 | 2026-09-09 17:25:08 GMT |
| aarch64 | `GET https://api2.cursor.sh/updates/api/download/stable/linux-arm64/sand` | 0.47.0 | `https://downloads.cursor.com/grokbot/stable/c1e7d7a46549956d25f53e9c0b9f59666e03aa3a/linux/arm64/Grok_Bot_0.47.0.AppImage` | 132859380 | 2026-09-09 17:24:45 GMT |

Both responses share `commitSha` `c1e7d7a46549956d25f53e9c0b9f59666e03aa3a`. Internal product name is `sand`. JSON includes `downloadUrl`, `debUrl`, `rpmUrl`, `version`, `commitSha` — **no SHA-256 field**. Multipart S3 etags are not Source Checksums. `https://cursor.com/download/bot` still lists 0.47.0. Treat 0.47.0 as current Stable Upstream Release for both arches; Source Checksums remain unresolved until a hash-bearing feed field or a pinned computed digest is chosen.

GitHub Pages still documents a 1 GB published-site cap and a 100 GB/month soft bandwidth limit. `ubuntu-24.04-arm` remains a standard GitHub-hosted runner label. No GitHub App, GPG key, secrets, Pages, or branch protection is configured.

### Affected Areas

- `openspec/changes/package-unofficial-grok-bot/` — this change's SDD artifacts
- New Flatpak manifest (`io.github.viniciosrab.GrokBot`) — Packaged Payload, finish-args, `SAND_DISABLE_UPDATES=1`
- New companion StatusNotifierItem sources — ADR 0003 process model
- New metainfo/desktop files — unofficial naming; Official Grok Bot Icon install
- New `tools/test.py`, `tests/`, `CMakeLists.txt` — documented in `docs/testing.md` but absent
- New `.github/workflows/` — feed detect, GitHub App PR, dual-arch validate, sign, Pages deploy
- `HANDOFF.md` — stale "wait for authorization" (do not rewrite ADRs)
- `docs/testing.md` — intended gate; implementation must make it true or stop claiming it

### Approaches

1. **Build-time AppImage verify + unpack into OSTree; KF6 companion on `org.kde.Platform`** — CI downloads the AppImage, verifies the pinned Source Checksum, unpacks squashfs, extracts the vendor icon, wraps launch with the companion and `SAND_DISABLE_UPDATES=1`, and publishes one Atomic Flatpak Release.
   - Pros: Matches ADR 0001 AppImage provenance; `flatpak update` is the only updater; icon is extracted not redesigned; OSTree payload does not depend on Cursor CDN at install; KF6 matches ADR 0003 and `docs/testing.md`.
   - Cons: Dual-arch AppImages (~126 MiB each) plus runtime refs pressure the 1 GB Pages cap unless only the current release is retained (already ADR 0002); companion and Electron sandbox finish-args need design-level care.
   - Effort: High

2. **Flatpak `extra-data` of the AppImage at install time** — manifest pins URL + checksum; the user runtime fetches Cursor CDN.
   - Pros: Smaller OSTree; simpler builder.
   - Cons: Install/update still hits vendor CDN; conflicts with sole `flatpak update` authority and SAND disable; extra-data cannot express the companion-before-start gate cleanly.
   - Effort: Medium

3. **Package vendor `.deb` instead of AppImage** — feed also returns `debUrl`.
   - Pros: Native file layout.
   - Cons: ADR 0001 names the AppImage as the Upstream Artifact; extra unpack/convert steps without tray benefit.
   - Effort: Medium

### Recommendation

Use approach 1 against the existing ADRs. Do not reopen unofficial labeling, atomic dual-arch publish, KDE-only tray, or vendor icon.

Implementation shape (proposal/design will specify):

- Detect Stable Upstream Releases from `https://api2.cursor.sh/updates/api/download/stable/linux-{x64,arm64}/sand` (not `x.ai/bot`).
- Pin version, URL, commit, and Source Checksum in git via the dedicated GitHub App PR (ADR 0002). If the feed still omits SHA-256, the pin job downloads the AppImage, computes SHA-256, and records that digest as the Source Checksum for later rebuilds — research must confirm this satisfies ADR 0001 or find the hash-bearing endpoint.
- Build on `ubuntu-24.04` and `ubuntu-24.04-arm`; merge/publish only when both validate.
- Require companion StatusNotifierItem registration before starting Grok Bot; no trayless fallback.
- Extract Official Grok Bot Icon from the AppImage (`hicolor/512x512/apps/grok-bot.png` is the path used by an unofficial AppImage integrator; confirm on first unpack).
- Keep current-only OSTree on GitHub Pages; tags/releases hold audit inputs.
- Add the documented `python3 tools/test.py` + CTest bootstrap in this change so later apply/verify have a live command; leave `strict_tdd: false` until that runner exists.

### Risks

- Stable download JSON still has no SHA-256; ADR 0001 expects a feed-supplied digest. Unresolved until research or an explicit pin-compute convention.
- Exact in-app updater URL vs `api/download/stable/.../sand` may differ; golden-stream fallback returns raw ELF and is a last resort.
- Electron/Chromium Flatpak finish-args (Wayland, portal, `/tmp`, zygote) are unset; wrong flags break the app or the sandbox.
- Companion-before-start plus `window-all-closed` → `app.quit()` can yield a tray with no window unless show/relaunch is correct (ADR 0003).
- GitHub App, GPG key, secrets, Pages, and branch protection are still missing; pipeline cannot go unattended until a human provisions them (wizard later, not this phase).
- `GITHUB_TOKEN` PRs still need approval; without the App, detect-and-pin loops stall.
- 1 GB Pages + ~250 MiB dual AppImage payload plus KDE runtime refs makes current-only retention mandatory; bandwidth 100 GB/month is a soft limit, not a hard blocker.
- `docs/testing.md` describes a runner that is absent; claiming that gate before adding files would be false.
- Single-PR delivery vs a likely >400-line first implementation; `sdd-tasks` must forecast budget even though strategy is `single-pr`.
- Redistribution remains accepted maintainer risk, not a blocker.

### Remaining unknowns

- Hash-bearing feed field (if any) and whether yumrepo RPM SHA-256 may be used (likely no: different artifact).
- `org.kde.Platform` version and finish-args for this Electron tree.
- Companion language/library (KF6 `KStatusNotifierItem` vs raw DBus) and DBus well-known name.
- How the Official Grok Bot Icon is stored inside 0.47.0 squashfs (confirm, do not invent).
- GitHub App permission set, GPG key custody, Pages URL, and branch-protection rules (ops, not design reopen).

### Research lanes

| Lane | Warranted | Why |
| --- | --- | --- |
| Upstream feed | Yes | Version/URLs confirmed; SHA-256 still missing; document exact pin contract |
| Flatpak runtime | Yes | Runtime ID/version and Electron finish-args are unset |
| StatusNotifierItem companion | Yes | Process model is ADR-settled; implementation stack is not |
| GitHub Pages / App | Partial | Pages limits revalidated; App/secrets are provisioning, not research |
| Icon extraction | Yes (short) | Confirm vendor PNG path on unpack; no redesign |

### Ready for Proposal

Yes, after or in parallel with targeted research on feed checksums, runtime/finish-args, and companion stack. Orchestrator should not interview for settled ADR/user constraints. Next human-facing work is proposal once research bytes exist or are explicitly deferred as pin-compute-SHA-256.
