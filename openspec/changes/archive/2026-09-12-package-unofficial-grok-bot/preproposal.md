# gentle-ai.sdd-preproposal/v1

- change: package-unofficial-grok-bot
- revision: 4
- artifact_store.mode: hybrid
- project: grok-bot-flatpak

## Exploration

- outcome: complete
- OpenSpec: openspec/changes/package-unofficial-grok-bot/exploration.md
- Engram: sdd/package-unofficial-grok-bot/explore

## Research request

- selected: true
- completion: mandatory
- requested_source_classes: [open-web]
- admission: admitted
- declared_grants:
  - documentation: []
  - open-web: [webfetch]
- observed_grants:
  - documentation: []
  - open-web: [webfetch]
- outcome: done
- question_4: withdrawn
- selected_questions: [1, 2, 3]
- OpenSpec evidence: openspec/changes/package-unofficial-grok-bot/research.md
- Engram evidence: sdd/package-unofficial-grok-bot/research
- evidence_revision: 3

## Product decisions

- status: confirmed
- notes: ADRs 0001–0003 remain closed. Research product-choice section is non-authoritative. Question 4 is withdrawn from the selected research request.
- confirmed:
  - source_checksum: CI-computed SHA-256 of each downloaded AppImage is the Source Checksum pin (integrity for rebuilds, not vendor attestation). aarch64 digest is computed at pin time. Observed x86_64 0.47.0 digest `c082fda9280c401b47cbbfe012f7b2b5cefd8d96c1291f80eec8561ad6db4af3` is a point-in-time observation, not a substitute for the pin job.
  - runtime: `org.kde.Platform` / `org.kde.Sdk` `6.11`
  - display_finish_args: `--socket=wayland` and `--socket=fallback-x11`
  - companion: separate Qt/KF6 process using `KStatusNotifierItem` with `--talk-name=org.kde.StatusNotifierWatcher`; show relaunches Grok Bot; quit terminates both
  - official_icon: extract vendor `usr/share/icons/hicolor/512x512/apps/grok-bot.png` (and the hicolor set). Do not use `resources/icon.png` as the desktop icon. Do not create or redesign an icon. Path confirmed by user-authorized AppImage unpack, not by research grants.

## Proposal readiness

- proposal_ready: true
- reasons:
  - selected research outcome is done (revision 3, questions 1–3; question 4 withdrawn)
  - product decisions are confirmed
  - hybrid research evidence read back at revision 3 in OpenSpec and Engram
