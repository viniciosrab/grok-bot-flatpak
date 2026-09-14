# Security Review: grok-bot-flatpak

## Scope

Complete static security review of all 63 Git-tracked files.

- Scan mode: repository
- Target kind: git_revision
- Target ID: target_sha256_3022e7e2ab058c823818a0c5eb3243e8dc40ca077d8e4d67e481b1ca341d73ab
- Revision: 1264bab662f9902f2074ae2317a9ae06d1f99394
- Inventory strategy: repository
- Included paths: .
- Excluded paths: none
- Runtime or test status: SDK-owned non-interactive Standard scan
- Artifacts reviewed: 63 Git-tracked files

Limitations and exclusions:
- Proprietary upstream Electron source and external GitHub settings were absent.

### Scan Summary

| Field | Value |
| --- | --- |
| Scan outcome | completed |
| Reportable findings | 4 |
| Severity mix | medium: 2, low: 2 |
| Confidence mix | high: 4 |
| Coverage | partial |
| Validation mode | baseline, architecture review, focused investigation, and parent validation |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

Unofficial dual-architecture Grok Bot Flatpak packaging with a Qt/KF6 protocol companion and privileged CI for upstream pinning, validation, signing, GitHub Releases, Pages deployment, and rollback. The proprietary Electron implementation is absent.

### Assets

- Upstream AppImage and published Flatpak integrity.
- GPG, GitHub App, workflow-token, release, and Pages authority.
- User session and protocol callback data.
- Flatpak sandbox permissions.

### Trust Boundaries

- Upstream feeds and artifact delivery enter unattended pin automation.
- Merged main commits enter validation and automatic release decisions.
- The release job imports signing authority and deploys Pages.
- Users consume the Pages remote with GPG verification disabled.
- Protocol URLs cross from the desktop into the companion and absent proprietary Electron receiver.

### Attacker Capabilities

- Compromised upstream infrastructure controls candidate metadata and bytes but not project signing.
- A merged contributor lacks separate release authority.
- A publication-origin attacker can replace served content after origin compromise.
- A compromised action publisher can change mutable-tag code.
- Same-user local processes can influence per-user state, but a stronger callback-disclosure boundary is unproven.

### Security Objectives

- Independently authenticate upstream executables.
- Bind explicit release intent to exact SHA and digests.
- Pin and isolate privileged CI dependencies.
- Require client verification of repository signatures.
- Preserve protocol and Flatpak boundaries.

### Assumptions

- Entire current 63-file Git repository was reviewed.
- No SECURITY.md, supplied threat model, scoped inventory, or knowledge base was provided.
- Proprietary Electron internals and external GitHub settings are unverified.
- HTTPS remains effective while the authenticated origin is uncompromised.

## Findings

| Finding | Severity | Confidence | Detailed write-up |
| --- | --- | --- | --- |
| [An ordinary main-branch merge can authorize a privileged release](#finding-1) | medium | high | inline below |
| [Upstream compromise is automatically converted into a signed release](#finding-2) | medium | high | inline below |
| [Mutable action tags run with signing and publication authority](#finding-3) | low | high | inline below |
| [Users install updates without verifying the repository signature](#finding-4) | low | high | inline below |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] An ordinary main-branch merge can authorize a privileged release

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The gate checks event, branch, SHA, tests, and version but no release-specific provenance. |
| Category | missing-authorization |
| CWE | CWE-862 |
| Affected lines | .github/workflows/validate.yml:19-23, .github/workflows/publish.yml:141-174, .github/workflows/publish.yml:221-249, .github/workflows/publish.yml:302-311 |

#### Summary

Any successful main push with a newer numeric pin version can become release intent without proof that it came from the pin workflow or a release-author approval.

#### Root Cause

Successful validation plus numeric version newness is incorrectly treated as explicit authorization to publish.

**All main pushes validate** — `.github/workflows/validate.yml:19-23`

Ordinary merged contributions and pin merges enter the same release chain.

```yaml
on:
  push:
    branches: [main]
  pull_request: {}
  workflow_dispatch: {}
```

**Version newness sets publication decision** — `.github/workflows/publish.yml:235-249`

A generic successful main chain plus newer version becomes sufficient release authorization.

```shell
if [ "${MODE}" = "auto" ] && [ "${IS_NEW}" != "true" ]; then
  echo "proceed=false" >> "${GITHUB_OUTPUT}"
  exit 0
fi
echo "proceed=true" >> "${GITHUB_OUTPUT}"
echo "sha=${SHA}" >> "${GITHUB_OUTPUT}"
echo "version=${VERSION}" >> "${GITHUB_OUTPUT}"
```

**Decision unlocks privileged release job** — `.github/workflows/publish.yml:302-311`

The decision grants release mutation, Pages, and OIDC authority.

```yaml
release:
  needs: [decide, build-x86_64, build-aarch64]
  if: ${{ needs.decide.outputs.proceed == 'true' }}
  permissions:
    contents: write
    pages: write
    id-token: write
  environment:
    name: github-pages
```

#### Validation

No pin-PR identity, allowed-file diff, signed intent record, or release-author approval exists in the automatic gate.

Validation method: static source trace

**All main pushes validate** — `.github/workflows/validate.yml:19-23`

Ordinary merged contributions and pin merges enter the same release chain.

```yaml
on:
  push:
    branches: [main]
  pull_request: {}
  workflow_dispatch: {}
```

**Version newness sets publication decision** — `.github/workflows/publish.yml:235-249`

A generic successful main chain plus newer version becomes sufficient release authorization.

```shell
if [ "${MODE}" = "auto" ] && [ "${IS_NEW}" != "true" ]; then
  echo "proceed=false" >> "${GITHUB_OUTPUT}"
  exit 0
fi
echo "proceed=true" >> "${GITHUB_OUTPUT}"
echo "sha=${SHA}" >> "${GITHUB_OUTPUT}"
echo "version=${VERSION}" >> "${GITHUB_OUTPUT}"
```

**Decision unlocks privileged release job** — `.github/workflows/publish.yml:302-311`

The decision grants release mutation, Pages, and OIDC authority.

```yaml
release:
  needs: [decide, build-x86_64, build-aarch64]
  if: ${{ needs.decide.outputs.proceed == 'true' }}
  permissions:
    contents: write
    pages: write
    id-token: write
  environment:
    name: github-pages
```

Counterevidence and remaining uncertainty:
- Exact-SHA and dual-architecture checks ensure quality and identity but not release intent.

Limitations:
- External branch and environment protection are unverified.

#### Dataflow

main merge -\> validate/X3 -\> version gate -\> release job

- **Source:** ordinary merged contribution

- **Sink:** signing and publication authority

- **Outcome:** unintended signed release

**All main pushes validate** — `.github/workflows/validate.yml:19-23`

Ordinary merged contributions and pin merges enter the same release chain.

```yaml
on:
  push:
    branches: [main]
  pull_request: {}
  workflow_dispatch: {}
```

**Version newness sets publication decision** — `.github/workflows/publish.yml:235-249`

A generic successful main chain plus newer version becomes sufficient release authorization.

```shell
if [ "${MODE}" = "auto" ] && [ "${IS_NEW}" != "true" ]; then
  echo "proceed=false" >> "${GITHUB_OUTPUT}"
  exit 0
fi
echo "proceed=true" >> "${GITHUB_OUTPUT}"
echo "sha=${SHA}" >> "${GITHUB_OUTPUT}"
echo "version=${VERSION}" >> "${GITHUB_OUTPUT}"
```

**Decision unlocks privileged release job** — `.github/workflows/publish.yml:302-311`

The decision grants release mutation, Pages, and OIDC authority.

```yaml
release:
  needs: [decide, build-x86_64, build-aarch64]
  if: ${{ needs.decide.outputs.proceed == 'true' }}
  permissions:
    contents: write
    pages: write
    id-token: write
  environment:
    name: github-pages
```

#### Reachability

Requires merge plus successful validation and X3.

- **Attacker:** contributor lacking separate release authority

- **Entry point:** ordinary main-branch merge

- **Outcome:** signed public release

#### Severity

**Medium** — A merged contributor change can trigger signed public release, but must pass review, merge, dual-architecture validation, and X3.

Additional runtime or deployment evidence could raise or lower this severity.

Impact assessment:
- **Level:** high
- **Why:** Contributor-controlled executable content can be publicly endorsed.

Likelihood assessment:
- **Level:** medium
- **Why:** A maintainer must merge the change, but no release-specific approval is required.

#### Remediation

Bind publication to exact approved pin-PR provenance and an allowed-file diff, or require protected release-author approval for the exact SHA and digests.

Tests:
- Ensure ordinary version-bump commits cannot set `proceed=true`.
- Require exact release-intent provenance before privileged jobs.

Preventive controls:
- Separate quality validation from release authorization.

<a id="finding-2"></a>

### [2] Upstream compromise is automatically converted into a signed release

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | Multiple independent reviews and parent validation establish the full feed-to-signing path. |
| Category | artifact-authenticity |
| CWE | CWE-345 |
| Affected lines | .github/workflows/pin.yml:97-136, .github/workflows/pin.yml:367-441, .github/workflows/publish.yml:351-356 |

#### Summary

Pin automation hashes the same AppImages delivered by upstream, auto-approves those digests, and later signs the package without an independent authenticity signal.

#### Root Cause

One unattended workflow observes upstream bytes, derives their trust data, and supplies the approval that authorizes them.

**Candidate downloads become their own pins** — `.github/workflows/pin.yml:126-136`

CI derives the only authoritative digests from the candidate executable bytes themselves.

```shell
curl -sSL --fail -o "${RUNNER_TEMP}/pin/x86_64.AppImage" "${X64_URL}"
curl -sSL --fail -o "${RUNNER_TEMP}/pin/aarch64.AppImage" "${ARM64_URL}"
X64_SHA="$(sha256sum "${RUNNER_TEMP}/pin/x86_64.AppImage" | cut -d ' ' -f 1)"
ARM64_SHA="$(sha256sum "${RUNNER_TEMP}/pin/aarch64.AppImage" | cut -d ' ' -f 1)"
```

**Automation supplies release approval** — `.github/workflows/pin.yml:436-444`

The same automated trust path supplies the required PR approval.

```shell
DECISION="$(gh pr view "${PR_NUMBER}" --json reviewDecision --jq .reviewDecision)"
if [ "${DECISION}" = "APPROVED" ]; then exit 0; fi
if ! gh pr review --approve "${PR_NUMBER}"; then exit 1; fi
```

**Accepted payload is project-signed** — `.github/workflows/publish.yml:351-356`

The resulting repository receives the project's signing endorsement.

```shell
ostree pull-local --repo=site arch-repos/repo-x86_64
ostree pull-local --repo=site arch-repos/repo-aarch64
printf '%s' "${GPG_KEY}" | gpg --import
flatpak build-update-repo --prune --gpg-sign="${KEY_ID}" site
```

#### Validation

Candidate downloads become committed pins, receive bot approval/auto-merge, and later reach project signing.

Validation method: static source trace

**Candidate downloads become their own pins** — `.github/workflows/pin.yml:126-136`

CI derives the only authoritative digests from the candidate executable bytes themselves.

```shell
curl -sSL --fail -o "${RUNNER_TEMP}/pin/x86_64.AppImage" "${X64_URL}"
curl -sSL --fail -o "${RUNNER_TEMP}/pin/aarch64.AppImage" "${ARM64_URL}"
X64_SHA="$(sha256sum "${RUNNER_TEMP}/pin/x86_64.AppImage" | cut -d ' ' -f 1)"
ARM64_SHA="$(sha256sum "${RUNNER_TEMP}/pin/aarch64.AppImage" | cut -d ' ' -f 1)"
```

**Automation supplies release approval** — `.github/workflows/pin.yml:436-444`

The same automated trust path supplies the required PR approval.

```shell
DECISION="$(gh pr view "${PR_NUMBER}" --json reviewDecision --jq .reviewDecision)"
if [ "${DECISION}" = "APPROVED" ]; then exit 0; fi
if ! gh pr review --approve "${PR_NUMBER}"; then exit 1; fi
```

**Accepted payload is project-signed** — `.github/workflows/publish.yml:351-356`

The resulting repository receives the project's signing endorsement.

```shell
ostree pull-local --repo=site arch-repos/repo-x86_64
ostree pull-local --repo=site arch-repos/repo-aarch64
printf '%s' "${GPG_KEY}" | gpg --import
flatpak build-update-repo --prune --gpg-sign="${KEY_ID}" site
```

Counterevidence and remaining uncertainty:
- Cross-feed agreement, host syntax checks, exact PR identity, and later digest verification provide integrity but not initial authenticity.

#### Dataflow

upstream bytes -\> self-derived digest -\> automated approval -\> signing

- **Source:** upstream release infrastructure

- **Sink:** GPG-signed Pages release

- **Outcome:** malicious payload gains project endorsement

**Candidate downloads become their own pins** — `.github/workflows/pin.yml:126-136`

CI derives the only authoritative digests from the candidate executable bytes themselves.

```shell
curl -sSL --fail -o "${RUNNER_TEMP}/pin/x86_64.AppImage" "${X64_URL}"
curl -sSL --fail -o "${RUNNER_TEMP}/pin/aarch64.AppImage" "${ARM64_URL}"
X64_SHA="$(sha256sum "${RUNNER_TEMP}/pin/x86_64.AppImage" | cut -d ' ' -f 1)"
ARM64_SHA="$(sha256sum "${RUNNER_TEMP}/pin/aarch64.AppImage" | cut -d ' ' -f 1)"
```

**Automation supplies release approval** — `.github/workflows/pin.yml:436-444`

The same automated trust path supplies the required PR approval.

```shell
DECISION="$(gh pr view "${PR_NUMBER}" --json reviewDecision --jq .reviewDecision)"
if [ "${DECISION}" = "APPROVED" ]; then exit 0; fi
if ! gh pr review --approve "${PR_NUMBER}"; then exit 1; fi
```

**Accepted payload is project-signed** — `.github/workflows/publish.yml:351-356`

The resulting repository receives the project's signing endorsement.

```shell
ostree pull-local --repo=site arch-repos/repo-x86_64
ostree pull-local --repo=site arch-repos/repo-aarch64
printf '%s' "${GPG_KEY}" | gpg --import
flatpak build-update-repo --prune --gpg-sign="${KEY_ID}" site
```

#### Reachability

Requires accepted metadata plus artifact delivery, or artifact delivery during a legitimate new release.

- **Attacker:** compromised upstream infrastructure

- **Entry point:** scheduled pin workflow

- **Outcome:** signed malicious release

#### Severity

**Medium** — Feed and artifact-delivery compromise can yield project-signed malicious releases; the external compromise prerequisite leaves likelihood uncertain.

Additional runtime or deployment evidence could raise or lower this severity.

Impact assessment:
- **Level:** high
- **Why:** Users can receive attacker code as an endorsed release.

Likelihood assessment:
- **Level:** medium
- **Why:** The source establishes the unattended path but not the probability of upstream compromise.

#### Remediation

Require vendor signatures or independently authenticated provenance; otherwise require an independent human release decision and validate final redirect origins.

Tests:
- Reject candidates without independently verified authenticity.
- Prevent pin automation from providing final release approval.

Preventive controls:
- Bind provenance to version, commit, architecture, URL, and digest.

<a id="finding-3"></a>

### [3] Mutable action tags run with signing and publication authority

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | The workflows visibly use only major tags at privileged boundaries. |
| Category | untrusted-dependency |
| CWE | CWE-829 |
| Affected lines | .github/workflows/pin.yml:71-76, .github/workflows/publish.yml:306-331, .github/workflows/publish.yml:353-356, .github/workflows/publish.yml:420-427 |

#### Summary

Secret-bearing and write-privileged jobs execute actions through mutable major tags, so compromised tag authority can replace artifacts, misuse credentials, or capture signing material.

#### Root Cause

Privileged reusable action code is identified by mutable release labels rather than reviewed immutable commits.

**Mutable action receives App private key** — `.github/workflows/pin.yml:71-76`

Code selected by mutable `v1` directly receives the App private key.

```yaml
- name: Mint GitHub App installation token
  uses: actions/create-github-app-token@v1
  with:
    app-id: ${{ secrets.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
```

**Mutable deployment actions hold publication authority** — `.github/workflows/publish.yml:420-427`

Mutable action code executes with Pages and OIDC permissions after signing.

```yaml
- name: Deploy the Flatpak Repository to Pages
  uses: actions/upload-pages-artifact@v3
  with:
    path: site
- name: Publish to the Pages environment
  uses: actions/deploy-pages@v4
```

#### Validation

Major-tag actions receive secrets or execute inside write-privileged jobs.

Validation method: static source trace

**Mutable action receives App private key** — `.github/workflows/pin.yml:71-76`

Code selected by mutable `v1` directly receives the App private key.

```yaml
- name: Mint GitHub App installation token
  uses: actions/create-github-app-token@v1
  with:
    app-id: ${{ secrets.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
```

**Mutable deployment actions hold publication authority** — `.github/workflows/publish.yml:420-427`

Mutable action code executes with Pages and OIDC permissions after signing.

```yaml
- name: Deploy the Flatpak Repository to Pages
  uses: actions/upload-pages-artifact@v3
  with:
    path: site
- name: Publish to the Pages environment
  uses: actions/deploy-pages@v4
```

Counterevidence and remaining uncertainty:
- The actions are GitHub-maintained and permissions are scoped.

Limitations:
- No external action compromise was investigated.

#### Dataflow

mutable tag -\> action code -\> secrets or Pages authority

- **Source:** compromised action publisher

- **Sink:** privileged CI job

- **Outcome:** credentials or release output compromised

**Mutable action receives App private key** — `.github/workflows/pin.yml:71-76`

Code selected by mutable `v1` directly receives the App private key.

```yaml
- name: Mint GitHub App installation token
  uses: actions/create-github-app-token@v1
  with:
    app-id: ${{ secrets.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
```

**Mutable deployment actions hold publication authority** — `.github/workflows/publish.yml:420-427`

Mutable action code executes with Pages and OIDC permissions after signing.

```yaml
- name: Deploy the Flatpak Repository to Pages
  uses: actions/upload-pages-artifact@v3
  with:
    path: site
- name: Publish to the Pages environment
  uses: actions/deploy-pages@v4
```

#### Reachability

Requires upstream action tag compromise.

- **Attacker:** compromised action publisher

- **Entry point:** workflow `uses:` reference

- **Outcome:** privileged CI execution

#### Severity

**Low** — Impact is severe, but exploitation requires compromise of GitHub-maintained action repositories or tag publishers.

Additional runtime or deployment evidence could raise or lower this severity.

Impact assessment:
- **Level:** high
- **Why:** App credentials, signing state, or Pages output may be compromised.

Likelihood assessment:
- **Level:** low
- **Why:** The publishers are GitHub-maintained.

#### Remediation

Pin every action to a reviewed full commit SHA and isolate signing from artifact and Pages actions.

Tests:
- Fail CI on non-SHA `uses:` references.
- Keep signing key unavailable to later reusable actions.

Preventive controls:
- Automate reviewed full-SHA updates.

<a id="finding-4"></a>

### [4] Users install updates without verifying the repository signature

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | The documented command explicitly disables GPG verification and states that the public key is not distributed. |
| Category | artifact-authenticity |
| CWE | CWE-494 |
| Affected lines | README.md:16-27, .github/workflows/publish.yml:353-356 |

#### Summary

The production instructions add the Pages Flatpak remote with `--no-gpg-verify`, so a compromised publication origin can substitute application updates despite repository signing.

#### Root Cause

The publisher creates a GPG signature but does not distribute its trust anchor and instructs clients to disable verification.

**Production remote disables GPG checks** — `README.md:16-17`

Clients following the supported setup accept the remote without repository-signature verification.

```shell
flatpak remote-add --user --if-not-exists --no-gpg-verify grok-bot \
  https://viniciosrab.github.io/grok-bot-flatpak/
```

**Publisher signs the repository** — `.github/workflows/publish.yml:353-356`

The release creates a signature, but the documented client path does not enforce it.

```shell
printf '%s' "${GPG_KEY}" | gpg --import
KEY_ID="$(gpg --list-secret-keys --with-colons | awk -F: '/^sec:/ {print $5; exit}')"
flatpak build-update-repo --prune --gpg-sign="${KEY_ID}" site
```

#### Validation

The signed publication and unverified installation paths are both explicit.

Validation method: static source trace

**Production remote disables GPG checks** — `README.md:16-17`

Clients following the supported setup accept the remote without repository-signature verification.

```shell
flatpak remote-add --user --if-not-exists --no-gpg-verify grok-bot \
  https://viniciosrab.github.io/grok-bot-flatpak/
```

**Publisher signs the repository** — `.github/workflows/publish.yml:353-356`

The release creates a signature, but the documented client path does not enforce it.

```shell
printf '%s' "${GPG_KEY}" | gpg --import
KEY_ID="$(gpg --list-secret-keys --with-colons | awk -F: '/^sec:/ {print $5; exit}')"
flatpak build-update-repo --prune --gpg-sign="${KEY_ID}" site
```

Counterevidence and remaining uncertainty:
- HTTPS remains effective while the authenticated origin is uncompromised.

Limitations:
- No live client installation was run.

#### Dataflow

Pages content -\> unverified Flatpak remote -\> application execution

- **Source:** compromised Pages content

- **Sink:** Flatpak install/update

- **Outcome:** replacement code executes

**Production remote disables GPG checks** — `README.md:16-17`

Clients following the supported setup accept the remote without repository-signature verification.

```shell
flatpak remote-add --user --if-not-exists --no-gpg-verify grok-bot \
  https://viniciosrab.github.io/grok-bot-flatpak/
```

#### Reachability

Requires control of the HTTPS publication origin.

- **Attacker:** distribution-channel attacker

- **Entry point:** Pages Flatpak remote

- **Outcome:** unauthenticated update acceptance

#### Severity

**Low** — Impact is replacement code execution inside the app sandbox, but exploitation requires compromise of GitHub Pages publication or its HTTPS origin.

Additional runtime or deployment evidence could raise or lower this severity.

Impact assessment:
- **Level:** high
- **Why:** Replacement application code executes with declared Flatpak permissions.

Likelihood assessment:
- **Level:** low
- **Why:** GitHub Pages or authenticated origin compromise is required.

#### Remediation

Publish the repository public key through an authenticated channel, remove `--no-gpg-verify`, and migrate existing remotes.

Tests:
- Reject production setup instructions containing `--no-gpg-verify`.
- Verify modified repository metadata or objects are rejected.

Preventive controls:
- Publish a key-bearing `.flatpakrepo` descriptor.

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| Flatpak client distribution authenticity | not recorded | Reported | GPG verification is disabled in the documented client setup. |
| Automated upstream pinning and approval | not recorded | Reported | Self-derived checksums are approved without independent authenticity. |
| Automatic release authorization | not recorded | Reported | Generic newer-version main pushes can authorize publication. |
| Privileged GitHub Action dependencies | not recorded | Reported | Major action tags are mutable. |
| Protocol singleton routing | not recorded | Rejected | Absent Electron receiver prevents proving callback capture; same-user state control alone is insufficient. |
| ASAR rewrite | not recorded | Rejected | Supported build executes the upstream artifact before the sidecar write; no additional authority is established. |
| Flatpak permissions and wrapper | not recorded | No issue found | Closed permissions grant no host filesystem or broad D-Bus access. |
| Exact-SHA build, tags, artifacts and rollback | not recorded | No issue found | Reviewed identity and rollback controls fail closed. |
| Tests, specs, templates, metadata and agent files | not recorded | No issue found | All remaining tracked files were reviewed without a distinct vulnerability. |

## Open Questions And Follow Up

- What security controls exist inside the absent proprietary Electron payload?
- Do external GitHub settings add release authorization controls not represented in source?
- Awaiting validation of proprietary Electron receiver reachability.
  - Follow-up prompt: Review deferred unit candidate-cold-singleton-socket and close its stated proof gap.
- Awaiting validation of proprietary Electron receiver reachability.
  - Follow-up prompt: Review deferred unit candidate-losing-lock-forward and close its stated proof gap.
- Awaiting validation of realistic boundary and incremental impact.
  - Follow-up prompt: Review deferred unit candidate-asar-tmp-symlink and close its stated proof gap.
