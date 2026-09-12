# Grok Bot Flatpak

This context describes the provenance and distribution language used by the
unofficial Grok Bot Flatpak project.

## Language

**Upstream Artifact**:
An application package published by the Grok Bot vendor and used as the verified source of a Flatpak build.
_Avoid_: Original binary, untouched application

**Source Checksum**:
The SHA-256 digest that identifies the exact Upstream Artifact approved for a build.
_Avoid_: Package checksum, authenticity proof

**Stable Upstream Release**:
A vendor-published version for which every supported architecture has an Upstream Artifact and Source Checksum in the stable channel.
_Avoid_: Latest version, detected version

**Packaged Payload**:
The application content installed by the Flatpak after declared, reproducible integration changes have been applied to an Upstream Artifact.
_Avoid_: Original binary

**Unofficial Flatpak**:
The independently maintained Flatpak distribution of Grok Bot, identified as `io.github.viniciosrab.GrokBot` and not endorsed by the upstream vendor.
_Avoid_: Official Flatpak, xAI Flatpak

**Flatpak Repository**:
The signed update source from which users install the Unofficial Flatpak and receive subsequent releases.
_Avoid_: GitHub release, download page

**Atomic Flatpak Release**:
A published version containing validated builds for every supported architecture as one indivisible update.
_Avoid_: Partial release, architecture release

**Official Grok Bot Icon**:
The Grok Bot application icon published by the vendor and used by the Unofficial Flatpak without redesigning or recreating it.
_Avoid_: Custom icon, recreated icon
