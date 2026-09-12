# Publish atomic releases through an auditable pipeline

The project will detect Stable Upstream Releases from the official update feed, propose pinned metadata through a dedicated GitHub App, and publish only after native `x86_64` and `aarch64` validation succeeds. Post-merge jobs will sign one Atomic Flatpak Release with a dedicated GPG key and deploy the pruned Flatpak Repository to GitHub Pages; this keeps releases unattended and reviewable while preventing partial publication and keeping signing secrets outside pull-request jobs.

The Flatpak Repository retains only its current release because GitHub Pages limits published sites to 1 GB. Tags, GitHub Releases, Source Checksums, and provenance records preserve audit and rollback inputs without retaining an unbounded OSTree history.
