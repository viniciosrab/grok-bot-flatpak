# Grok Bot Flatpak Handoff

## Current state

The design discussion is complete, but implementation is explicitly deferred until the user authorizes it. Do not create the Flatpak manifest, scripts, workflows, tests, signing configuration, or release infrastructure without that authorization.

The repository currently contains documentation changes only. They are uncommitted.

## Read first

- [`CONTEXT.md`](./CONTEXT.md) defines the canonical domain language. Use these terms consistently and do not turn this glossary into a specification.
- [`docs/adr/0001-verify-upstream-and-adapt-payload.md`](./docs/adr/0001-verify-upstream-and-adapt-payload.md) records the provenance and payload-adaptation boundary.
- [`docs/adr/0002-publish-atomic-releases-automatically.md`](./docs/adr/0002-publish-atomic-releases-automatically.md) records the automated release, signing, architecture, hosting, and retention decisions.
- [`docs/adr/0003-require-kde-tray-availability.md`](./docs/adr/0003-require-kde-tray-availability.md) records the mandatory KDE tray contract.

Do not restate these decisions in new planning documents. Link to the relevant artifact instead.

## Verified facts

- The public landing page at `https://x.ai/bot` returned Cloudflare `403` to non-browser automation during this session and should not be scraped for release detection.
- Grok Bot's packaged updater uses `https://api2.cursor.sh/updates` and returns a versioned download URL plus an upstream SHA-256 for each architecture.
- On 2026-09-11, the stable feed reported version `0.47.0` for both `x86_64` and `aarch64`. Treat this as time-sensitive and query the feed again before implementation.
- The application recognizes `SAND_DISABLE_UPDATES=1`; the future Flatpak must use it so `flatpak update` remains the sole update authority.
- The verified Grok Bot 0.47.0 `x86_64` and `aarch64` Upstream Artifacts do not provide a system tray item: neither Electron main-process bundle constructs `Tray` or references StatusNotifierItem, and both use the same Linux `window-all-closed` handler that calls `app.quit()`.
- The Unofficial Flatpak must therefore provide a companion StatusNotifierItem. It will remain available after Grok Bot exits, relaunch the application through show, and terminate both through quit; see ADR 0003.
- GitHub Pages currently limits a published site to 1 GB and has a soft bandwidth limit of 100 GB per month. Revalidate these limits before implementation.
- Public GitHub-hosted native ARM Linux runners were available under `ubuntu-24.04-arm` during this session.
- Workflow-created PRs using the repository `GITHUB_TOKEN` enter an approval-required state. The settled design therefore requires a dedicated, least-privilege GitHub App with short-lived installation tokens.
- No GitHub App, GPG key, repository secret, Pages environment, or branch protection has been configured.

## User constraints

- The package must remain clearly unofficial.
- Redistribution permission is an accepted maintainer risk and is not a release blocker.
- KDE StatusNotifierItem tray integration is mandatory. There is no supported trayless fallback.
- The Unofficial Flatpak must use the Official Grok Bot Icon. Do not create, recreate, or redesign an application icon.
- Releases must cover `x86_64` and `aarch64` atomically.
- Do not begin implementation until the user explicitly authorizes it.

## Worktree notes

- `CONTEXT.md`, `docs/adr/`, and this handoff are currently untracked.
- `.codegraph/` was initialized during the session and is also untracked.
- `.atl/` was already present as an unrelated untracked directory; do not modify or remove it without an explicit request.
- No commits or pull requests were created.

## Suggested skills

- Call the Skill tool for `work-unit-commits` when implementation is authorized, before splitting the manifest, integration code, tests, and workflows into reviewable units.
- Call the Skill tool for `domain-modeling` if any terminology or settled architecture decision is reopened.
- Call the Skill tool for `cognitive-doc-design` when extending maintainer or installation documentation.
- Call the Skill tool for `branch-pr` only when the user requests a pull request.

## Next action

Wait for explicit implementation authorization. Once received, inspect the current worktree and upstream feed again, then implement the companion StatusNotifierItem and the remaining packaging against the existing glossary and ADRs rather than reopening settled choices.
