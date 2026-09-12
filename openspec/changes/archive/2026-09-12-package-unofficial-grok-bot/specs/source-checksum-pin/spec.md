# Source Checksum Pin Specification

## Purpose

Define sand-feed selection and integrity checks per arch.

## Requirements

### Requirement: Pin and verify source artifacts

The project MUST identify each Upstream Artifact by sand-feed version, URL, and `commitSha`. CI SHALL verify a SHA-256 Source Checksum per architecture. This establishes integrity, not vendor attestation.

#### Scenario: Pinned source is accepted

- GIVEN a sand feed matches its declared version, URL, and `commitSha`
- WHEN CI computes the architecture-specific SHA-256 digest
- THEN the digest matches and the artifact may enter the build

#### Scenario: Pinned bytes change

- GIVEN the feed metadata matches but the downloaded bytes differ
- WHEN CI verifies the Source Checksum
- THEN verification fails closed and that architecture is not built or published
