# Packaged Payload Specification

## Purpose

Define the unofficial Flatpak payload. Provenance remains in `CONTEXT.md` and ADR 0001.

## Requirements

### Requirement: Build the unofficial payload

The build MUST produce `io.github.viniciosrab.GrokBot` using KDE Platform and SDK 6.11. It SHALL unpack the approved Upstream Artifact into OSTree, support Wayland with fallback X11, set `SAND_DISABLE_UPDATES=1`, and use vendor hicolor icons without replacement artwork.

#### Scenario: Valid payload is assembled

- GIVEN a verified Upstream Artifact for a supported architecture
- WHEN the Flatpak build completes
- THEN the payload has unofficial identity, KDE 6.11, both sockets, disabled updates, and vendor icons

#### Scenario: Required payload evidence is absent

- GIVEN an artifact lacks the vendor icon or cannot launch with KDE/Electron integration
- WHEN payload validation runs
- THEN validation fails and the payload is rejected
