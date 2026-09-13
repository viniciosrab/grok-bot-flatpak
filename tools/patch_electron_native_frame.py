#!/usr/bin/env python3
"""Fail-closed ASAR patch: native Linux frame, no in-content window controls.

Packed vendor BrowserWindow chrome lives in app.asar. Linux currently
creates a frameless window (`frame: false`, `titleBarStyle: "default"`)
and the renderer then draws in-content minimize/maximize/close buttons.
KDE already supplies server-side decorations, so those extra controls
duplicate the Plasma titlebar.

Electron Window Controls Overlay (`titleBarOverlay`) is Windows-only in
this payload and requires a non-default `titleBarStyle`. The Linux
transform keeps the default title bar style, enables a native frame, and
skips the in-content control widget. It never adds `titleBarOverlay`.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
from collections.abc import Iterable

NATIVE_FRAME_FIND = b'{frame:!1,titleBarStyle:"default"}'
NATIVE_FRAME_REPLACE = b'{frame:!0,titleBarStyle:"default"}'
IN_CONTENT_CONTROLS_FIND = b"if(o)return null;let C,T,E,R,M;if(e[15]!==r)"
IN_CONTENT_CONTROLS_REPLACE = b"if(1)return null;let C,T,E,R,M;if(e[15]!==r)"
WINDOWS_WCO_MARK = b'titleBarStyle:"hidden",titleBarOverlay:'
MAC_FRAME_MARK = b'titleBarStyle:"hiddenInset"'

PATCHES = (
    (NATIVE_FRAME_FIND, NATIVE_FRAME_REPLACE),
    (IN_CONTENT_CONTROLS_FIND, IN_CONTENT_CONTROLS_REPLACE),
)


class TransformError(RuntimeError):
    """The expected upstream ASAR pattern is missing or ambiguous."""


def _require_same_length_patches(patches: Iterable[tuple[bytes, bytes]]) -> None:
    for find, replace in patches:
        if not find or find == replace:
            raise TransformError("invalid patch: empty or unchanged pattern")
        if len(find) != len(replace):
            raise TransformError(
                "invalid patch: replacements must keep ASAR member size"
            )


def _walk_files(node: dict, prefix: str = "") -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for name, child in node.get("files", {}).items():
        path = f"{prefix}/{name}" if prefix else name
        if "files" in child:
            out.extend(_walk_files(child, path))
        else:
            out.append((path, child))
    return out


def read_asar(blob: bytes) -> tuple[dict, int, int, int]:
    """Return header, JSON start, JSON length, and file-data offset."""
    if len(blob) < 16:
        raise TransformError("asar is too small to contain a header")
    header_size_payload = struct.unpack_from("<I", blob, 0)[0]
    header_pickle_size = struct.unpack_from("<I", blob, 4)[0]
    if header_size_payload != 4:
        raise TransformError("unexpected asar header-size pickle")
    if 8 + header_pickle_size > len(blob):
        raise TransformError("truncated asar header")
    json_len = struct.unpack_from("<I", blob, 12)[0]
    json_start = 16
    if json_start + json_len > len(blob):
        raise TransformError("truncated asar JSON header")
    header = json.loads(blob[json_start : json_start + json_len].decode("utf-8"))
    data_offset = 8 + header_pickle_size
    return header, json_start, json_len, data_offset


def _member_bytes(blob: bytes, meta: dict, data_offset: int) -> bytes:
    if meta.get("unpacked"):
        raise TransformError("refusing to patch an unpacked ASAR member")
    if "offset" not in meta or "size" not in meta:
        raise TransformError("asar member is missing offset/size")
    start = data_offset + int(meta["offset"])
    size = int(meta["size"])
    end = start + size
    if end > len(blob):
        raise TransformError("asar member extends past the archive")
    return blob[start:end]


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index


def _value_span_for_key(text: str, object_start: int, key: str) -> tuple[int, int]:
    decoder = json.JSONDecoder()
    index = _skip_ws(text, object_start)
    if index >= len(text) or text[index] != "{":
        raise TransformError("expected a JSON object")
    index += 1
    while True:
        index = _skip_ws(text, index)
        if index >= len(text):
            raise TransformError("truncated JSON object")
        if text[index] == "}":
            raise TransformError("missing JSON key %s" % key)
        parsed_key, key_end = decoder.raw_decode(text, index)
        index = _skip_ws(text, key_end)
        if index >= len(text) or text[index] != ":":
            raise TransformError("malformed JSON object")
        value_start = _skip_ws(text, index + 1)
        _value, value_end = decoder.raw_decode(text, value_start)
        if parsed_key == key:
            return value_start, value_end
        index = _skip_ws(text, value_end)
        if index < len(text) and text[index] == ",":
            index += 1
            continue
        raise TransformError("missing JSON key %s" % key)


def _member_span(json_text: str, path: str) -> tuple[int, int]:
    start = _skip_ws(json_text, 0)
    start, _end = _value_span_for_key(json_text, start, "files")
    parts = path.split("/")
    for i, part in enumerate(parts):
        start, end = _value_span_for_key(json_text, start, part)
        if i != len(parts) - 1:
            start, end = _value_span_for_key(json_text, start, "files")
    return start, end


def _block_count(size: int, block_size: int) -> int:
    return (size + block_size - 1) // block_size


def _block_hashes(data: bytes, block_size: int) -> list[str]:
    return [
        _sha256_hex(data[index : index + block_size])
        for index in range(0, len(data), block_size)
    ]


def _validate_integrity(integrity: object, size: int) -> int:
    if not isinstance(integrity, dict):
        raise TransformError("asar member integrity is missing")
    if integrity.get("algorithm") != "SHA256":
        raise TransformError("asar member integrity algorithm is not SHA256")
    block_size = integrity.get("blockSize")
    if type(block_size) is not int or block_size <= 0:
        raise TransformError("asar member integrity blockSize is malformed")
    digest = integrity.get("hash")
    blocks = integrity.get("blocks")
    if not _is_sha256_hex(digest):
        raise TransformError("asar member integrity hash is malformed")
    if not isinstance(blocks, list) or not blocks:
        raise TransformError("asar member integrity blocks are malformed")
    if any(not _is_sha256_hex(block) for block in blocks):
        raise TransformError("asar member integrity blocks are malformed")
    expected = _block_count(size, block_size)
    if expected <= 0 or len(blocks) != expected:
        raise TransformError("asar member integrity block count is malformed")
    return block_size


def refresh_member_integrity(json_text: str, path: str, data: bytes) -> str:
    """Rewrite one member's integrity object; keep the JSON header length."""
    member_start, _member_end = _member_span(json_text, path)
    try:
        integrity_start, integrity_end = _value_span_for_key(
            json_text, member_start, "integrity"
        )
    except TransformError as exc:
        raise TransformError("asar member integrity is missing") from exc
    integrity_text = json_text[integrity_start:integrity_end]
    try:
        integrity = json.loads(integrity_text)
    except json.JSONDecodeError as exc:
        raise TransformError("asar member integrity is malformed") from exc
    block_size = _validate_integrity(integrity, len(data))
    compact = json.dumps(integrity, separators=(",", ":"))
    if compact != integrity_text:
        raise TransformError("asar member integrity is not compact JSON")
    updated = dict(integrity)
    updated["hash"] = _sha256_hex(data)
    updated["blocks"] = _block_hashes(data, block_size)
    if len(updated["blocks"]) != len(integrity["blocks"]):
        raise TransformError("asar member integrity block count changed")
    new_text = json.dumps(updated, separators=(",", ":"))
    if len(new_text) != len(integrity_text):
        raise TransformError("asar JSON header size changed")
    return json_text[:integrity_start] + new_text + json_text[integrity_end:]


def apply_native_frame_patches(blob: bytes) -> bytes:
    """Patch packed members in place. Fail if a pattern is absent or repeated."""
    _require_same_length_patches(PATCHES)
    header, json_start, json_len, data_offset = read_asar(blob)
    members = _walk_files(header)
    planned: list[tuple[str, dict, bytes, bytes]] = []
    for find, replace in PATCHES:
        hits: list[tuple[str, dict, int]] = []
        for path, meta in members:
            if meta.get("unpacked"):
                continue
            content = _member_bytes(blob, meta, data_offset)
            count = content.count(find)
            if count:
                hits.append((path, meta, count))
        if len(hits) != 1 or hits[0][2] != 1:
            raise TransformError(
                "expected exactly one ASAR occurrence of %r, found %s"
                % (find, [(path, count) for path, _, count in hits])
            )
        planned.append((hits[0][0], hits[0][1], find, replace))

    patched = bytearray(blob)
    json_text = blob[json_start : json_start + json_len].decode("utf-8")
    touched: set[str] = set()
    for path, meta, find, replace in planned:
        start = data_offset + int(meta["offset"])
        size = int(meta["size"])
        original = bytes(patched[start : start + size])
        if original.count(find) != 1:
            raise TransformError("refusing to rewrite %s with a non-unique patch" % path)
        updated = original.replace(find, replace, 1)
        if len(updated) != size or find in updated:
            raise TransformError("patch did not consume %r in %s" % (find, path))
        patched[start : start + size] = updated
        json_text = refresh_member_integrity(json_text, path, updated)
        touched.add(path)

    encoded_json = json_text.encode("utf-8")
    if len(encoded_json) != json_len:
        raise TransformError("asar JSON header size changed")
    patched[json_start : json_start + json_len] = encoded_json

    result = bytes(patched)
    if WINDOWS_WCO_MARK not in result or MAC_FRAME_MARK not in result:
        raise TransformError("refusing to drop macOS/Windows window chrome")
    if NATIVE_FRAME_FIND in result:
        raise TransformError("Linux native-frame pattern is still present")
    if IN_CONTENT_CONTROLS_FIND in result:
        raise TransformError("Linux in-content control pattern is still present")
    if NATIVE_FRAME_REPLACE not in result or IN_CONTENT_CONTROLS_REPLACE not in result:
        raise TransformError("native-frame replacements are missing")
    if not touched:
        raise TransformError("no ASAR members were patched")
    return result


def member_content(blob: bytes, path: str) -> bytes:
    header, _json_start, _json_len, data_offset = read_asar(blob)
    for member, meta in _walk_files(header):
        if member == path:
            return _member_bytes(blob, meta, data_offset)
    raise TransformError("missing ASAR member %s" % path)


def member_meta(blob: bytes, path: str) -> dict:
    header, _json_start, _json_len, _data_offset = read_asar(blob)
    for member, meta in _walk_files(header):
        if member == path:
            return meta
    raise TransformError("missing ASAR member %s" % path)


def write_asar(
    files: dict[str, bytes],
    *,
    block_size: int = 4194304,
    with_integrity: bool = True,
) -> bytes:
    """Build a minimal packed ASAR for tests. Directories are implied by paths."""
    entries: list[tuple[str, bytes]] = sorted(files.items())
    offset = 0
    tree: dict = {"files": {}}
    payload = bytearray()
    for path, content in entries:
        parts = path.split("/")
        node = tree
        for part in parts[:-1]:
            node = node["files"].setdefault(part, {"files": {}})
        entry: dict = {
            "size": len(content),
            "offset": str(offset),
        }
        if with_integrity:
            entry["integrity"] = {
                "algorithm": "SHA256",
                "hash": _sha256_hex(content),
                "blockSize": block_size,
                "blocks": _block_hashes(content, block_size),
            }
        node["files"][parts[-1]] = entry
        payload.extend(content)
        offset += len(content)

    json_bytes = json.dumps(tree, separators=(",", ":")).encode("utf-8")
    string_payload = struct.pack("<I", len(json_bytes)) + json_bytes + b"\x00"
    pad = (4 - (len(string_payload) % 4)) % 4
    pickle_payload = string_payload + (b"\x00" * pad)
    header_pickle = struct.pack("<I", len(pickle_payload)) + pickle_payload
    header_size_pickle = struct.pack("<I", 4) + struct.pack("<I", len(header_pickle))
    return header_size_pickle + header_pickle + bytes(payload)


def patch_asar_file(path: str) -> None:
    with open(path, "rb") as handle:
        original = handle.read()
    patched = apply_native_frame_patches(original)
    fd, tmp_name = None, path + ".tmp"
    try:
        fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(patched)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if fd is not None:
            os.close(fd)
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or not args[0]:
        sys.stderr.write(
            "usage: patch_electron_native_frame.py /path/to/app.asar\n"
        )
        return 1
    path = args[0]
    try:
        patch_asar_file(path)
    except (OSError, TransformError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        sys.stderr.write("patch_electron_native_frame: %s\n" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
