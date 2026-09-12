# Atomic Flatpak Release Specification

## Purpose

Define one indivisible multi-architecture publication.

## Requirements

### Requirement: Publish only validated atomic releases

CI MUST validate all supported architectures before publication. It SHALL publish one Atomic Flatpak Release only after all pass, retain only the current Pages OSTree, and express pin and publication workflows as code. A failed release MUST be recoverable from tagged content.

#### Scenario: Both architectures pass

- GIVEN every supported architecture has a validated Packaged Payload
- WHEN the release workflow publishes
- THEN one Atomic Flatpak Release containing both architectures is published

#### Scenario: One architecture fails

- GIVEN at least one architecture fails source, payload, or runtime validation
- WHEN the release workflow reaches its publication gate
- THEN no release is published and tagged prior content remains the recovery target
