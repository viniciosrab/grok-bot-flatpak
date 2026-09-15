#!/usr/bin/env python3
"""Consumer-side verifier for pinned source artifacts.

Single seam for the download-and-prove step: parse the pinned URL and
SHA-256 digest for one architecture from data/pins.yml, download the
bytes fresh (never from cache), and fail closed unless the bytes are
non-empty and match the pin. Both validate arch jobs call this module
instead of duplicating grep/curl/sha256sum shell, and the digest-proof
tests exercise this same implementation instead of a hashlib mirror.

Interface:
    verify_bytes_against_digest(data, digest) -> bool
    verify_pinned_artifact(pins_path, arch, fetch=None) -> (url, digest)
    CLI: python3 tools/source_checksum.py --pins data/pins.yml --arch x86_64

Error modes: every failure raises SourceChecksumError with a clear
message (missing file, malformed pins, missing pin, bad URL/digest,
network error, empty bytes, digest mismatch). The CLI maps that to
exit 1; exit 0 means the bytes matched the pin.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable

SUPPORTED_ARCHES = ("x86_64", "aarch64")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_FETCH_TIMEOUT_SECONDS = 60


class SourceChecksumError(Exception):
    """Fail-closed verdict for any step of the pinned-artifact proof."""


def verify_bytes_against_digest(data: bytes, digest: str) -> bool:
    """Accept only bytes whose SHA-256 matches the pinned digest."""
    if not isinstance(data, (bytes, bytearray)):
        return False
    if not isinstance(digest, str) or not HEX64_RE.match(digest):
        return False
    actual = hashlib.sha256(bytes(data)).hexdigest()
    return hmac.compare_digest(actual, digest)


def _parse_pins_mapping(text: str) -> dict:
    """Parse flat/nested `key: value` mappings (indent-nested, no lists).

    Raises SourceChecksumError on anything outside that subset so
    pins.yml stays machine-checkable without a YAML dependency.
    """
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split(" # ", 1)[0].rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if "\t" in line:
            raise SourceChecksumError(f"line {lineno}: tabs are not allowed")
        if stripped.startswith("- "):
            raise SourceChecksumError(
                f"line {lineno}: lists are not supported in pins.yml"
            )
        if ":" not in stripped:
            raise SourceChecksumError(f"line {lineno}: expected `key: value`")
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if not key or " " in key:
            raise SourceChecksumError(f"line {lineno}: invalid key {key!r}")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if key in parent:
            raise SourceChecksumError(f"line {lineno}: duplicate key {key!r}")
        if value == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            parent[key] = value
    return root


def _load_pinned_source(pins_path: str, arch: str) -> tuple[str, str]:
    """Return the pinned (url, sha256) for one arch, or fail closed."""
    if arch not in SUPPORTED_ARCHES:
        raise SourceChecksumError(
            f"unsupported arch {arch!r}: expected one of {', '.join(SUPPORTED_ARCHES)}"
        )
    if not os.path.isfile(pins_path):
        raise SourceChecksumError(f"pins file not found: {pins_path}")
    try:
        with open(pins_path, "r", encoding="utf-8") as handle:
            pins = _parse_pins_mapping(handle.read())
    except (OSError, UnicodeDecodeError) as exc:
        raise SourceChecksumError(f"cannot read pins file {pins_path}: {exc}") from exc
    arches = pins.get("architectures")
    if not isinstance(arches, dict) or arch not in arches:
        raise SourceChecksumError(f"missing {arch} pin in {pins_path}")
    entry = arches[arch]
    if not isinstance(entry, dict):
        raise SourceChecksumError(f"missing {arch} pin in {pins_path}")
    url = entry.get("url", "")
    digest = entry.get("sha256", "")
    if not isinstance(url, str) or not url or not url.startswith("https://"):
        raise SourceChecksumError(f"missing {arch} pin in {pins_path}")
    if not isinstance(digest, str) or not HEX64_RE.match(digest):
        raise SourceChecksumError(f"missing {arch} digest in {pins_path}")
    return url, digest


def _download_artifact(url: str) -> bytes:
    """Download URL fresh (no cache) or fail closed on any network error."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "grok-bot-flatpak-source-checksum"}
    )
    try:
        with urllib.request.urlopen(
            request, timeout=_FETCH_TIMEOUT_SECONDS
        ) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise SourceChecksumError(f"failed to download {url}: {exc}") from exc


def verify_pinned_artifact(
    pins_path: str,
    arch: str,
    fetch: Callable[[str], bytes] | None = None,
) -> tuple[str, str]:
    """Prove the pinned artifact for one arch; return (url, digest).

    Parses the pin, downloads the bytes fresh on every call (no cache
    that could skip the proof), rejects empty bytes, and rejects any
    digest mismatch. The fetch dependency is injectable so tests cross
    this same seam with stub bytes; production passes None for the
    urllib download. Raises SourceChecksumError on any failure.
    """
    url, digest = _load_pinned_source(pins_path, arch)
    downloader = fetch if fetch is not None else _download_artifact
    try:
        data = downloader(url)
    except SourceChecksumError:
        raise
    except Exception as exc:
        raise SourceChecksumError(f"failed to download {url}: {exc}") from exc
    if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
        raise SourceChecksumError(f"empty artifact from {url}")
    if not verify_bytes_against_digest(data, digest):
        raise SourceChecksumError(f"sha256 mismatch for {arch} artifact from {url}")
    return url, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a pinned source artifact against data/pins.yml."
    )
    parser.add_argument("--pins", default="data/pins.yml")
    parser.add_argument("--arch", required=True, choices=SUPPORTED_ARCHES)
    args = parser.parse_args(argv)
    try:
        url, _digest = verify_pinned_artifact(args.pins, args.arch)
    except SourceChecksumError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"verified {args.arch} source from {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
