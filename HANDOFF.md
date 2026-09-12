# Grok Bot Flatpak Handoff

## Current state

Implementation of change `package-unofficial-grok-bot` is committed on
branch `feat/package-unofficial-grok-bot`; PR #2 is open to `main`.
The Flatpak manifest, KF6 tray companion, Source Checksum pins,
validation and publication workflows, test runner, and CTest wiring all
exist; `python3 tools/test.py` passes. The release chain is now fully
automatic on GitHub-hosted runners: successful validate on main ->
automatic hosted X3 -> publish. X3 graphical launch proof is implemented
but remains unproven until the main-line chain runs (see
below). `strict_tdd` remains `false` per the change contract.

## Read first

- [`CONTEXT.md`](./CONTEXT.md) defines the canonical domain language. Use these terms consistently and do not turn this glossary into a specification.
- [`docs/adr/0001-verify-upstream-and-adapt-payload.md`](./docs/adr/0001-verify-upstream-and-adapt-payload.md) records the provenance and payload-adaptation boundary.
- [`docs/adr/0002-publish-atomic-releases-automatically.md`](./docs/adr/0002-publish-atomic-releases-automatically.md) records the automated release, signing, architecture, hosting, and retention decisions.
- [`docs/adr/0003-require-kde-tray-availability.md`](./docs/adr/0003-require-kde-tray-availability.md) records the mandatory KDE tray contract.

Do not restate these decisions in new planning documents. Link to the relevant artifact instead.

## Verified facts

- The public landing page returned Cloudflare `403` to non-browser automation during the design session and is never scraped for release detection; only the two sand feeds are queried.
- Grok Bot's packaged updater uses `https://api2.cursor.sh/updates` and returns a versioned download URL plus `commitSha` for each architecture. The stable sand feed publishes no SHA-256 field, so CI-computed SHA-256 digests serve as the Source Checksum pins (integrity, not vendor attestation).
- On 2026-09-12 the stable feed reported version `0.47.0` with `commitSha` `c1e7d7a46549956d25f53e9c0b9f59666e03aa3a` for both arches. Both Upstream Artifacts were downloaded and hashed: `x86_64` (132115801 bytes) pins to `c082fda9280c401b47cbbfe012f7b2b5cefd8d96c1291f80eec8561ad6db4af3`, `aarch64` (132859380 bytes) pins to `8ecf3d80f3d8c848ea522c07f92d57f9b43794607d2f99652ea05ccd82aea62e`. The pin job re-verifies both digests on every run.
- The application recognizes `SAND_DISABLE_UPDATES=1`; the Flatpak sets it so `flatpak update` remains the sole update authority.
- The verified Grok Bot 0.47.0 `x86_64` and `aarch64` Upstream Artifacts do not provide a system tray item: neither Electron main-process bundle constructs `Tray` or references StatusNotifierItem, and both use the same Linux `window-all-closed` handler that calls `app.quit()`.
- The Unofficial Flatpak therefore ships a companion StatusNotifierItem (`companion/src/main.cpp`). It remains available after Grok Bot exits, relaunches the application through show, and terminates both through quit; see ADR 0003. Absence of `StatusNotifierWatcher` exits nonzero; there is no trayless fallback.
 - The manifest builds on `org.kde.Platform`/`org.kde.Sdk` 6.11 with zypak as a module (not an Electron BaseApp base). X3 graphical launch proof is automatic on GitHub-hosted runners but remains unproven until the main-line chain runs: successful `validate` on `main` triggers the `x3` workflow (dual-arch, fail-closed), which starts a real `plasmashell` process on `Xvfb` under a real D-Bus session via the single shared `tools/prove_x3.sh` proof both architecture jobs call, waits for the real `StatusNotifierWatcher` name, then launches the Packaged Payload through the companion and proves the companion stays alive. `validate.yml` still proves the dual-arch build plus the watcher-gate rejection headlessly (`QT_QPA_PLATFORM=offscreen` negative test only, NOT X3 launch success); positive X3 proof runs only in the automatic hosted `x3` workflow, and `publish.yml` runs only after successful automatic `x3` on `main`, so neither architecture is X3-validated yet.
- GitHub Pages currently limits a published site to 1 GB and has a soft bandwidth limit of 100 GB per month. Revalidate these limits before the first publication.
- Public GitHub-hosted native ARM Linux runners were available under `ubuntu-24.04-arm` during this session.
- Workflow-created PRs using the repository `GITHUB_TOKEN` enter an approval-required state. The design therefore requires a dedicated, least-privilege GitHub App with short-lived installation tokens.
- No GitHub App, GPG key, repository secret, Pages environment, or branch protection has been configured.

## Human provisioning requirements

A human must provision the following before unattended operation; workflows
name these secrets only and fail closed while any is missing:

- GitHub App with least-privilege contents read/write + pull requests read/write permissions, installed on the repository: `APP_ID`, `APP_PRIVATE_KEY`.
- Dedicated GPG signing key for the Flatpak Repository: `GPG_KEY`.
- GitHub Pages environment (`github-pages`) serving the published OSTree site.
- Branch protection on the default branch (pin PRs merge only after validation passes).

## Rollback boundary

- Before merge: revert the uncommitted worktree (`git status` shows only the new implementation files plus this handoff).
- After merge, before publication: a failed validation or missing X3 proof publishes nothing (`publish.yml` listens to successful `x3` runs only); fix forward on the pin or payload side.
- After publication: never publish one architecture. Republish the newest `flatpak/deployed-<version>-rN` marker's current-only OSTree as the recovery target; `flatpak/<version>-rN` release tags and GitHub Releases hold the audit inputs.

## User constraints

- The package must remain clearly unofficial.
- Redistribution permission is an accepted maintainer risk and is not a release blocker.
- KDE StatusNotifierItem tray integration is mandatory. There is no supported trayless fallback.
- The Unofficial Flatpak must use the Official Grok Bot Icon. Do not create, recreate, or redesign an application icon.
- Releases must cover `x86_64` and `aarch64` atomically.

## Worktree notes

- Work is on branch `feat/package-unofficial-grok-bot` with the implementation committed; PR #2 targets `main`.
- `.codegraph/` was initialized during the design session and is untracked.
- `.atl/` is unrelated and ignored; do not modify or remove it without an explicit request.

## Suggested skills

- Call the Skill tool for `work-unit-commits` when implementation is authorized, before splitting the manifest, integration code, tests, and workflows into reviewable units.
- Call the Skill tool for `domain-modeling` if any terminology or settled architecture decision is reopened.
- Call the Skill tool for `cognitive-doc-design` when extending maintainer or installation documentation.
- Call the Skill tool for `branch-pr` only when the user requests a pull request.

## Next action

Run independent SDD verification (`sdd-verify`) against the five specs, then archive the change. After archival, provision the GitHub App, GPG key, Pages environment, and branch protection above, and only then request a pull request.
