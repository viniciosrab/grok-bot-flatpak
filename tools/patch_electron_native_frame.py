#!/usr/bin/env python3
"""Fail-closed ASAR patch: native Linux frame, no in-content window controls,
close-to-hide lifecycle, and second-instance reveal.

Packed vendor BrowserWindow chrome lives in app.asar. Linux currently
creates a frameless window (`frame: false`, `titleBarStyle: "default"`)
and the renderer then draws in-content minimize/maximize/close buttons.
KDE already supplies server-side decorations, so those extra controls
duplicate the Plasma titlebar.

Electron Window Controls Overlay (`titleBarOverlay`) is Windows-only in
this payload and requires a non-default `titleBarStyle`. The Linux
transform keeps the default title bar style, enables a native frame, and
skips the in-content control widget. It never adds `titleBarOverlay`.

Lifecycle (byte-exact vendor shapes from dist/electron-main/main-core.cjs,
the only member containing them): closing the main window must hide it
while Electron keeps running, so the existing KF6 tray Show (a second
exec that the running single instance focuses) reveals the already-running
window quickly. The existing `closed` listener is kept and a `close`
interceptor is appended that prevents the default close and hides unless
a `before-quit` flag was armed; the flag is armed by a `once` listener
prepended to the untouched `window-all-closed` quit line, so an explicit
quit still destroys and quits while the tray Quit action still terminates
Electron and the companion at the process-group level. Tray Quit signals
only the tracked leader first, and a SIGTERM listener converts that
signal into graceful app.quit, so vendor `before-quit` cleanup shuts down
the detached local-exec daemon before the process exits. Every
second-instance activation runs the existing focus chain (restore when
minimized, show, then focus) before handling links, including URL-bearing
activations that previously handled links without revealing. The native
application menu bar is hidden by default through the documented
`autoHideMenuBar` window option at the verified creation seam, so the
native frame and titlebar stay intact while Alt still reveals the
untouched application menu with its roles and shortcuts.

Hardware-acceleration restart (byte-exact vendor shape from
dist/electron-main/main-app.cjs, the only member containing it): the
toggle persists then calls `relaunchDesktop`, which is
`app.relaunch()` plus `app.quit()`. GPU policy is launch-only, and
vendor `before-quit` preventDefault while draining the detached
local-exec daemon aborts that quit. The hide-to-tray interceptor then
sees the armed quitting flag and can destroy/recreate the window
without exiting, so Chromium never relaunches. A same-length swap to
`app.exit()` terminates this instance so the stored GPU preference
applies on the new process. `exit()` skips before-quit daemon drain.

Member sizes may grow: the archive is rebuilt by splicing only the
changed size, offset, and integrity values into the original JSON header,
so unpacked entries and unknown fields are preserved byte for byte. Every
pattern must occur exactly once or the transform fails closed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys
from collections.abc import Callable, Iterable

NATIVE_FRAME_FIND = b'{frame:!1,titleBarStyle:"default"}'
NATIVE_FRAME_REPLACE = b'{frame:!0,titleBarStyle:"default"}'
IN_CONTENT_CONTROLS_FIND = b"if(o)return null;let C,T,E,R,M;if(e[15]!==r)"
IN_CONTENT_CONTROLS_REPLACE = b"if(1)return null;let C,T,E,R,M;if(e[15]!==r)"
WINDOWS_WCO_MARK = b'titleBarStyle:"hidden",titleBarOverlay:'
MAC_FRAME_MARK = b'titleBarStyle:"hiddenInset"'
# Close interception: byte-exact vendor shape from the packed main-process
# bundle (dist/electron-main/main-core.cjs, the only member containing it).
# The existing `closed` listener is preserved and a `close` interceptor is
# appended: it prevents the default close and hides the window unless the
# `before-quit` flag below was armed, so renderer signaling still fires on
# a real close while a hidden window keeps its renderer ready.
CLOSE_INTERCEPT_FIND = b's.on("closed",()=>{Ch.markRendererNotReady()})'
CLOSE_INTERCEPT_REPLACE = (
    b's.on("closed",()=>{Ch.markRendererNotReady()}),'
    b's.on("close",e=>{he.app.quitting||(e.preventDefault(),s.hide())})'
)
# Quit arming: byte-exact vendor `window-all-closed` line from the same
# bundle (also the only member containing it). A one-shot `before-quit`
# listener is prepended to arm the flag; the quit line itself is untouched,
# so it still quits once windows really close during an explicit quit.
QUIT_ARM_FIND = (
    b'he.app.on("window-all-closed",()=>{process.platform!=="darwin"'
    b'&&he.app.quit()})'
)
QUIT_ARM_REPLACE = (
    b'he.app.once("before-quit",()=>{he.app.quitting=!0}),'
    b'he.app.on("window-all-closed",()=>{process.platform!=="darwin"'
    b'&&he.app.quit()})'
)
# Second-instance reveal: byte-exact vendor shape from the packed
# main-process bundle (dist/electron-main/main-core.cjs, the only member
# containing it). The upstream activation handler only reveals on the
# empty-argv path and merely handles links otherwise, so a hidden window
# stays invisible for URL-bearing activations such as protocol callbacks.
# The patched shape runs the existing focus target (restore when
# minimized, show, then focus) on every activation before handling links.
# Trailing empty statements keep the replacement the same byte length.
SECOND_INSTANCE_REVEAL_FIND = (
    b's=(c,l)=>{let d=Ph(r,l);if(d.length===0){t.focus();return}'
    b'for(let u of d)o.handleCandidate(u,"second-instance")}'
)
SECOND_INSTANCE_REVEAL_REPLACE = (
    b's=(c,l)=>{let d=Ph(r,l);t.focus();if(d.length!==0)'
    b'for(let u of d)o.handleCandidate(u,"second-instance")};;;;;;;;'
)

# Hidden menu bar: byte-exact vendor shape from the single BrowserWindow
# creation site in the packed main-process bundle
# (dist/electron-main/main-core.cjs, the only member containing it). The
# documented `autoHideMenuBar` option is inserted right after the window
# options spread, so it wins over any spread value while the native frame,
# the titlebar, and the application menu itself stay untouched; Alt still
# reveals the menu on Linux.
MENU_HIDE_FIND = b"new rs.BrowserWindow({...a.windowOptions,"
MENU_HIDE_REPLACE = b"new rs.BrowserWindow({...a.windowOptions,autoHideMenuBar:!0,"
# Graceful quit bridge: byte-exact vendor shape from the single-instance
# lock line in the packed main-process bundle
# (dist/electron-main/main-core.cjs, the only member containing it). An OS
# SIGTERM currently kills Electron raw through the bundled signal-exit
# helper, skipping vendor `before-quit` cleanup (including the detached
# local-exec daemon shutdown). The appended listener converts SIGTERM into
# graceful app.quit instead, so the existing quit path terminates the
# daemon before the process exits.
SIGTERM_QUIT_BRIDGE_FIND = b"ru||he.app.quit();"
SIGTERM_QUIT_BRIDGE_REPLACE = (
    b"ru||he.app.quit();process.on(\"SIGTERM\",()=>{he.app.quit()});"
)
# Hardware-acceleration relaunch: byte-exact vendor shape from the packed
# main-process bundle (dist/electron-main/main-app.cjs, the only member
# containing it). Same-length swap: quit() after relaunch() is aborted by
# vendor before-quit preventDefault, so the process often stays alive and
# GPU flags never change. exit() terminates this instance. It skips the
# before-quit daemon drain.
RELAUNCH_QUIT_FIND = b"ye.app.relaunch(),ye.app.quit()"
RELAUNCH_QUIT_REPLACE = b"ye.app.relaunch(),ye.app.exit()"
# Exact anchors for the currently pinned 0.51.0 payload. These are captured
# from the packed x86_64 and aarch64 app.asar members. The archive bytes differ
# elsewhere by architecture, but these approved member-local anchors are
# identical; membership remains exact and fail-closed.
CURRENT_CONTROLS_FIND = (
    b'if(c==="darwin")return null;if(c==="win32"){let W;'
    b'e[12]===Symbol.for("react.memo_cache_sentinel")?(W={display:"none"},'
    b'e[12]=W):W=e[12];let Y;return e[13]!==w?'
    b'(Y=f.jsx("div",{"aria-hidden":!0,className:"sand-window-controls",'
    b'ref:w,style:W}),e[13]=w,e[14]=Y):Y=e[14],Y}'
    b'if(o)return null;let C,A,E,R,N;if(e[15]!==r)'
)
CURRENT_CONTROLS_REPLACE = CURRENT_CONTROLS_FIND.replace(
    b"if(o)return null", b"if(1)return null", 1
)
CURRENT_CLOSE_FIND = (
    b's.on("closed",()=>{Dh.markRendererNotReady()});let c=AP({window:TP(s),'
    b'app:{onceBeforeQuit:d=>he.app.once("before-quit",d)}})'
)
CURRENT_CLOSE_REPLACE = (
    b's.on("closed",()=>{Dh.markRendererNotReady()}),'
    b's.on("close",e=>{he.app.quitting||(e.preventDefault(),s.hide())});'
    b'let c=AP({window:TP(s),app:{onceBeforeQuit:d=>he.app.once("before-quit",d)}})'
)
CURRENT_SECOND_INSTANCE_FIND = (
    b's=(c,l)=>{let d=Mh(r,l);if(d.length===0){t.focus();return}'
    b'for(let u of d)o.handleCandidate(u,"second-instance")}'
)
CURRENT_SECOND_INSTANCE_REPLACE = (
    b's=(c,l)=>{let d=Mh(r,l);t.focus();if(d.length!==0)'
    b'for(let u of d)o.handleCandidate(u,"second-instance")};;;;;;;;'
)
CURRENT_MENU_HIDE_FIND = (
    b'i=new is.BrowserWindow({...a.windowOptions,title:is.app.getName(),'
    b'icon:pP({platform:process.platform,isPackaged:is.app.isPackaged,'
    b'resourcesPath:process.resourcesPath,devIconPath:t}),backgroundColor:e,'
    b'...rP({isMac:o,isWindows:process.platform==="win32",backgroundColor:e}),'
    b'webPreferences:{contextIsolation:!0,nodeIntegration:!1,preload:'
    b'vp.default.join(Sy,Tp({isPackaged:is.app.isPackaged,devCapability:r})),'
    b'sandbox:!0,webviewTag:!0}})'
)
CURRENT_MENU_HIDE_REPLACE = (
    CURRENT_MENU_HIDE_FIND.replace(
        b"{...a.windowOptions,",
        b"{...a.windowOptions,autoHideMenuBar:!0,",
        1,
    )
)
CURRENT_SIGTERM_FIND = (
    b'var su=!he.app.isPackaged||he.app.requestSingleInstanceLock();'
    b'su||he.app.quit();'
)
CURRENT_SIGTERM_REPLACE = (
    b'var su=!he.app.isPackaged||he.app.requestSingleInstanceLock();'
    b'su||he.app.quit();process.on("SIGTERM",()=>{he.app.quit()});'
)
CURRENT_RELAUNCH_FIND = (
    b"hardwareAccelerationEnabledAtLaunch:kjt,relaunchDesktop:()=>{let B="
    b"ne.environment.restartExitCode;if(B!=null){zZ(B);return}"
    b"me.app.relaunch(),me.app.quit()},getMachineId:()=>it()"
)
CURRENT_RELAUNCH_REPLACE = CURRENT_RELAUNCH_FIND.replace(
    b"me.app.relaunch(),me.app.quit()",
    b"me.app.relaunch(),me.app.exit()",
    1,
)
PATCHES = (
    (NATIVE_FRAME_FIND, NATIVE_FRAME_REPLACE),
    (IN_CONTENT_CONTROLS_FIND, IN_CONTENT_CONTROLS_REPLACE),
    (SECOND_INSTANCE_REVEAL_FIND, SECOND_INSTANCE_REVEAL_REPLACE),
    (RELAUNCH_QUIT_FIND, RELAUNCH_QUIT_REPLACE),
)
# Anchor-preserving appends: the anchor FIND stays in the output inside its
# REPLACE, so post-guards require the REPLACE present and the anchor
# exactly once instead of requiring the anchor to vanish.
EXTENSIONS = (
    (CLOSE_INTERCEPT_FIND, CLOSE_INTERCEPT_REPLACE),
    (QUIT_ARM_FIND, QUIT_ARM_REPLACE),
    (MENU_HIDE_FIND, MENU_HIDE_REPLACE),
    (SIGTERM_QUIT_BRIDGE_FIND, SIGTERM_QUIT_BRIDGE_REPLACE),
)


class TransformError(RuntimeError):
    """The expected upstream ASAR pattern is missing or ambiguous."""


_MINIFIED_IDENTIFIER = rb"[A-Za-z_$][A-Za-z0-9_$]*"


class StructuralPatch:
    """A minifier-tolerant patch over one verified JavaScript shape."""

    __slots__ = ("name", "pattern", "replacement")

    def __init__(
        self,
        name: str,
        pattern: re.Pattern,
        replacement: Callable[[re.Match], bytes],
    ) -> None:
        self.name = name
        self.pattern = pattern
        self.replacement = replacement


class NativePatchRule:
    """An exact pinned patch with an optional structural fallback."""

    __slots__ = (
        "name",
        "find",
        "replace",
        "structural",
        "extension",
        "member_path",
        "structural_path",
        "structural_path_pattern",
        "exact_paths",
        "exact_pairs",
        "structural_auto",
    )

    def __init__(
        self,
        name: str,
        find: bytes,
        replace: bytes,
        structural: StructuralPatch | None = None,
        extension: bool = False,
        member_path: str | None = None,
        structural_path: str | None = None,
        structural_path_pattern: re.Pattern[str] | None = None,
        exact_paths: tuple[str, ...] = (),
        exact_pairs: tuple[tuple[bytes, bytes], ...] = (),
        structural_auto: bool = False,
    ) -> None:
        self.name = name
        self.find = find
        self.replace = replace
        self.structural = structural
        self.extension = extension
        self.member_path = member_path
        self.structural_path = structural_path
        self.structural_path_pattern = structural_path_pattern
        self.exact_paths = exact_paths
        self.exact_pairs = ((find, replace),) + exact_pairs
        self.structural_auto = structural_auto


# Renderer entry bundles are code-split per release (0.51.0 shipped
# `index-<hash>.js`, 0.53.0 ships `index-u-<hash>.js` next to hundreds of
# `chunk-*.js` splits). The controls component always lives in the single
# entry bundle, never in a chunk, a stylesheet, or a `-copy` decoy.
RENDERER_ENTRY_BUNDLE_RE = re.compile(r"^dist/renderer/assets/index-[^/]*\.js$")


PatchCandidate = tuple[str, int, int, re.Match[bytes] | None, bytes | None]
AppliedPatch = tuple[NativePatchRule, str, bytes, bool]


def _balanced_braces(data: bytes) -> bool:
    """Check brace balance while ignoring JS string literals."""
    depth = 0
    quote: int | None = None
    escaped = False
    index = 0
    while index < len(data):
        byte = data[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif byte == 92:  # backslash
                escaped = True
            elif byte == quote:
                quote = None
        elif byte in (34, 39, 96):  # ", ', `
            quote = byte
        elif byte == 123:  # {
            depth += 1
        elif byte == 125:  # }
            depth -= 1
            if depth < 0:
                return False
        index += 1
    return quote is None and depth == 0


def _controls_structural_replacement(match: re.Match[bytes]) -> bytes:
    """Rewrite only the Linux hidden guard after the win32 controls block."""
    full = match.group(0)
    hidden = match.group("hidden")
    win32 = match.group("win32")
    if b"sand-window-controls" not in win32:
        raise TransformError(
            "structural patch Linux in-content controls missing invariant"
        )
    if not _balanced_braces(win32):
        raise TransformError(
            "structural patch Linux in-content controls unbalanced block"
        )
    win32_end = match.end("win32") - match.start(0)
    prefix, suffix = full[:win32_end], full[win32_end:]
    rewritten_suffix, count = re.subn(
        rb"if\s*\(\s*" + re.escape(hidden) + rb"\s*\)\s*return\s+null",
        b"if(1)return null",
        suffix,
        count=1,
    )
    if count != 1:
        raise TransformError(
            "structural patch Linux in-content controls produced no change"
        )
    return prefix + rewritten_suffix


_CONTROLS_STRUCTURAL = StructuralPatch(
    "Linux in-content controls",
    re.compile(
        rb"if\s*\(\s*(?P<platform>"
        + _MINIFIED_IDENTIFIER
        + rb")\s*(?:===|==)\s*[\"']darwin[\"']\s*\)\s*return\s+null\s*;"
        + rb"\s*if\s*\(\s*(?P=platform)\s*(?:===|==)\s*[\"']win32[\"']\s*\)\s*"
        + rb"\{(?P<win32>[\s\S]{0,8000}?sand-window-controls[\s\S]{0,8000}?)\}"
        + rb"\s*if\s*\(\s*(?P<hidden>"
        + _MINIFIED_IDENTIFIER
        + rb")\s*\)\s*return\s+null\s*;"
        + rb"\s*(?:var|let|const)\s+"
        + _MINIFIED_IDENTIFIER
        + rb"(?:\s*,\s*"
        + _MINIFIED_IDENTIFIER
        + rb")*\s*;"
        + rb"\s*if\s*\(\s*(?P<state>"
        + _MINIFIED_IDENTIFIER
        + rb")\s*\[\s*\d+\s*\]\s*(?:!==|!=)\s*"
        + _MINIFIED_IDENTIFIER
        + rb"\s*\)"
    ),
    _controls_structural_replacement,
)


_CLOSE_STRUCTURAL = StructuralPatch(
    "close-to-hide lifecycle",
    re.compile(
        rb'(?P<anchor>(?P<window>'
        + _MINIFIED_IDENTIFIER
        + rb')\.on\("closed",\(\)=>\{(?P<activation>'
        + _MINIFIED_IDENTIFIER
        + rb')\.markRendererNotReady\(\)\}\))'
        rb'(?P<suffix>;let '
        + _MINIFIED_IDENTIFIER
        + rb'=(?P<factory>'
        + _MINIFIED_IDENTIFIER
        + rb')\(\{window:(?P<window_factory>'
        + _MINIFIED_IDENTIFIER
        + rb')\((?P=window)\),app:\{onceBeforeQuit:(?P<callback>'
        + _MINIFIED_IDENTIFIER
        + rb')=>(?P<app>'
        + _MINIFIED_IDENTIFIER
        + rb')\.app\.once\("before-quit",(?P=callback)\)\}\}\))'
    ),
    lambda match: match.group("anchor")
    + b','
    + match.group("window")
    + b'.on("close",e=>{'
    + match.group("app")
    + b'.app.quitting||(e.preventDefault(),'
    + match.group("window")
    + b'.hide())})'
    + match.group("suffix"),
)


_QUIT_ARM_STRUCTURAL = StructuralPatch(
    "window-all-closed quit arming",
    re.compile(
        rb'(?P<app>'
        + _MINIFIED_IDENTIFIER
        + rb')\.app\.on\("window-all-closed",\(\)=>\{process\.platform!=="darwin"'
        rb'&&(?P=app)\.app\.quit\(\)\}\)'
    ),
    lambda match: match.group("app")
    + b'.app.once("before-quit",()=>{'
    + match.group("app")
    + b'.app.quitting=!0}),'
    + match.group(0),
)


_SECOND_INSTANCE_STRUCTURAL = StructuralPatch(
    "second-instance reveal",
    re.compile(
        rb'(?P<handler>'
        + _MINIFIED_IDENTIFIER
        + rb')=\((?P<first>'
        + _MINIFIED_IDENTIFIER
        + rb'),(?P<second>'
        + _MINIFIED_IDENTIFIER
        + rb')\)=>\{let (?P<list>'
        + _MINIFIED_IDENTIFIER
        + rb')=(?P<parser>'
        + _MINIFIED_IDENTIFIER
        + rb')\((?P<source>'
        + _MINIFIED_IDENTIFIER
        + rb'),(?P<input>'
        + _MINIFIED_IDENTIFIER
        + rb')\);if\((?P=list)\.length===0\)\{(?P<target>'
        + _MINIFIED_IDENTIFIER
        + rb')\.focus\(\);return\}for\(let (?P<item>'
        + _MINIFIED_IDENTIFIER
        + rb') of (?P=list)\)(?P<dispatcher>'
        + _MINIFIED_IDENTIFIER
        + rb')\.handleCandidate\((?P=item),"second-instance"\)\}'
    ),
    lambda match: match.group("handler")
    + b"=("
    + match.group("first")
    + b","
    + match.group("second")
    + b")=>{let "
    + match.group("list")
    + b"="
    + match.group("parser")
    + b"("
    + match.group("source") + b"," + match.group("input")
    + b");"
    + match.group("target")
    + b".focus();if("
    + match.group("list")
    + b".length!==0)for(let "
    + match.group("item")
    + b" of "
    + match.group("list")
    + b")"
    + match.group("dispatcher")
    + b'.handleCandidate('
    + match.group("item")
    + b',"second-instance")};;;;;;;;',
)


_MENU_HIDE_STRUCTURAL = StructuralPatch(
    "BrowserWindow menu hiding",
    # The prefix alone also matches unrelated utility windows, so the match
    # additionally proves the main window through co-occurring behavioral
    # invariants from the verified 0.51.0/0.53.0 spans: a title derived from
    # the app name plus the secure webPreferences set. The zero-width
    # lookaheads keep the match span on the prefix (no swallowing hazard)
    # while tolerating identifier churn and option reordering.
    re.compile(
        rb'(?P<window>'
        + _MINIFIED_IDENTIFIER
        + rb')=new (?P<electron>'
        + _MINIFIED_IDENTIFIER
        + rb')\.BrowserWindow\(\{\.\.\.(?P<options>'
        + _MINIFIED_IDENTIFIER
        + rb')\.windowOptions,'
        + rb'(?=[\s\S]{0,2000}?title:)'
        + rb'(?=[\s\S]{0,2000}?\.app\.getName\(\))'
        + rb'(?=[\s\S]{0,2000}?backgroundColor)'
        + rb'(?=[\s\S]{0,2000}?webPreferences:)'
        + rb'(?=[\s\S]{0,2000}?sandbox:!0)'
        + rb'(?=[\s\S]{0,2000}?webviewTag:!0)'
    ),
    lambda match: match.group(0) + b"autoHideMenuBar:!0,",
)


_SIGTERM_STRUCTURAL = StructuralPatch(
    "single-instance graceful SIGTERM bridge",
    re.compile(
        rb'(?P<decl>var|let|const)[ \t]+(?P<lock>'
        + _MINIFIED_IDENTIFIER
        + rb')=!?(?P<app>'
        + _MINIFIED_IDENTIFIER
        + rb')\.app\.isPackaged\|\|(?P=app)\.app\.requestSingleInstanceLock\(\);'
        rb'(?P=lock)\|\|(?P=app)\.app\.quit\(\);'
    ),
    lambda match: match.group(0).replace(
        match.group("lock")
        + b"||"
        + match.group("app")
        + b".app.quit();",
        match.group("lock")
        + b"||"
        + match.group("app")
        + b'.app.quit();process.on("SIGTERM",()=>{'
        + match.group("app")
        + b'.app.quit()});',
        1,
    ),
)


# The verified restart guard has one nested block. Keeping that block balanced
# while excluding unmatched braces prevents this rule from crossing the
# relaunchDesktop function's closing brace into a neighboring property.
_RELAUNCH_STRUCTURAL = StructuralPatch(
    "hardware-acceleration relaunch",
    re.compile(
        rb'relaunchDesktop:\(\)=>\{(?=[^{}]{0,800}restartExitCode)'
        rb'(?P<body>(?:[^{}]|\{[^{}]*\}){0,800}?)(?P<app>'
        + _MINIFIED_IDENTIFIER
        + rb')\.app\.relaunch\(\),(?P=app)\.app\.quit\(\)'
    ),
    lambda match: match.group(0).replace(
        match.group("app") + b".app.relaunch()," + match.group("app") + b".app.quit()",
        match.group("app") + b".app.relaunch()," + match.group("app") + b".app.exit()",
        1,
    ),
)


NATIVE_PATCH_RULES = (
    NativePatchRule(
        "native Linux frame",
        NATIVE_FRAME_FIND,
        NATIVE_FRAME_REPLACE,
        member_path="dist/electron-main/main-core.cjs",
    ),
    NativePatchRule(
        "Linux in-content controls",
        CURRENT_CONTROLS_FIND,
        CURRENT_CONTROLS_REPLACE,
        _CONTROLS_STRUCTURAL,
        exact_paths=(
            "dist/renderer/assets/index-B7CuLxVI.js",
        ),
        exact_pairs=(),
        structural_path_pattern=RENDERER_ENTRY_BUNDLE_RE,
        structural_auto=True,
    ),
    NativePatchRule(
        "second-instance reveal",
        SECOND_INSTANCE_REVEAL_FIND,
        SECOND_INSTANCE_REVEAL_REPLACE,
        _SECOND_INSTANCE_STRUCTURAL,
        member_path="dist/electron-main/main-core.cjs",
        exact_pairs=((CURRENT_SECOND_INSTANCE_FIND, CURRENT_SECOND_INSTANCE_REPLACE),),
        structural_auto=True,
    ),
    NativePatchRule(
        "hardware-acceleration relaunch",
        RELAUNCH_QUIT_FIND,
        RELAUNCH_QUIT_REPLACE,
        _RELAUNCH_STRUCTURAL,
        member_path="dist/electron-main/main-app.cjs",
        exact_pairs=((CURRENT_RELAUNCH_FIND, CURRENT_RELAUNCH_REPLACE),),
        structural_auto=True,
    ),
    NativePatchRule(
        "close-to-hide lifecycle",
        CLOSE_INTERCEPT_FIND,
        CLOSE_INTERCEPT_REPLACE,
        _CLOSE_STRUCTURAL,
        extension=True,
        member_path="dist/electron-main/main-core.cjs",
        exact_pairs=((CURRENT_CLOSE_FIND, CURRENT_CLOSE_REPLACE),),
        structural_auto=True,
    ),
    NativePatchRule(
        "window-all-closed quit arming",
        QUIT_ARM_FIND,
        QUIT_ARM_REPLACE,
        _QUIT_ARM_STRUCTURAL,
        extension=True,
        member_path="dist/electron-main/main-core.cjs",
    ),
    NativePatchRule(
        "BrowserWindow menu hiding",
        MENU_HIDE_FIND,
        MENU_HIDE_REPLACE,
        _MENU_HIDE_STRUCTURAL,
        extension=True,
        member_path="dist/electron-main/main-core.cjs",
        exact_pairs=((CURRENT_MENU_HIDE_FIND, CURRENT_MENU_HIDE_REPLACE),),
        structural_auto=True,
    ),
    NativePatchRule(
        "single-instance graceful SIGTERM bridge",
        SIGTERM_QUIT_BRIDGE_FIND,
        SIGTERM_QUIT_BRIDGE_REPLACE,
        _SIGTERM_STRUCTURAL,
        extension=True,
        member_path="dist/electron-main/main-core.cjs",
        exact_pairs=((CURRENT_SIGTERM_FIND, CURRENT_SIGTERM_REPLACE),),
        structural_auto=True,
    ),
)


def _validate_patch_pair(find: bytes, replace: bytes) -> None:
    if (
        not isinstance(find, bytes)
        or not isinstance(replace, bytes)
        or not find
        or find == replace
    ):
        raise TransformError("invalid patch: empty or unchanged pattern")


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


def _packed_contents(blob: bytes) -> dict[str, bytes]:
    header, _json_start, _json_len, data_offset = read_asar(blob)
    return {
        path: _member_bytes(blob, meta, data_offset)
        for path, meta in _walk_files(header)
        if not meta.get("unpacked")
    }


def _same_semantic_occurrence(
    first: PatchCandidate,
    second: PatchCandidate,
) -> bool:
    """Treat exact and structural detections as one occurrence only when spans contain one another."""
    return first[0] == second[0] and (
        (first[1] <= second[1] and second[2] <= first[2])
        or (second[1] <= first[1] and first[2] <= second[2])
    )


def _semantic_candidates(
    exact_candidates: list[PatchCandidate],
    structural_candidates: list[PatchCandidate],
) -> list[PatchCandidate]:
    """Merge only a one-to-one exact/structural view of one occurrence."""
    components: list[list[PatchCandidate]] = []
    for candidate in exact_candidates + structural_candidates:
        related = [
            index
            for index, component in enumerate(components)
            if any(
                _same_semantic_occurrence(candidate, existing)
                for existing in component
            )
        ]
        if not related:
            components.append([candidate])
            continue
        merged = [candidate]
        for index in reversed(related):
            merged[0:0] = components.pop(index)
        components.append(merged)

    semantic: list[PatchCandidate] = []
    for component in components:
        exact = [candidate for candidate in component if candidate[3] is None]
        structural = [candidate for candidate in component if candidate[3] is not None]
        if len(exact) == 1 and len(structural) == 1:
            semantic.append(exact[0])
        else:
            semantic.extend(component)
    return semantic


def _member_matches(rule: NativePatchRule, path: str) -> bool:
    if rule.exact_paths:
        return path in rule.exact_paths
    if rule.member_path is None:
        return True
    return path == rule.member_path


def _structural_member_matches(rule: NativePatchRule, path: str) -> bool:
    if rule.structural_path_pattern is not None:
        return bool(rule.structural_path_pattern.match(path))
    if rule.structural_path is not None:
        return path == rule.structural_path
    return _member_matches(rule, path)


def _apply_native_frame_rules(
    blob: bytes,
    *,
    allow_structural_fallback: bool = False,
) -> tuple[bytes, list[AppliedPatch]]:
    """Apply exact pinned rules, with automatic semantic matching.

    Rules marked structural_auto tolerate minifier churn through a stable
    path-scoped semantic matcher (the renderer controls rule follows the
    single versioned entry bundle instead of a pinned hash filename).
    Remaining structural rules stay explicitly enabled manual diagnostics.
    """
    header, json_start, json_len, data_offset = read_asar(blob)
    contents = {
        path: _member_bytes(blob, meta, data_offset)
        for path, meta in _walk_files(header)
        if not meta.get("unpacked")
    }
    applied: list[AppliedPatch] = []

    for rule in NATIVE_PATCH_RULES:
        if rule.structural_path_pattern is not None:
            scoped = sorted(
                path
                for path in contents
                if rule.structural_path_pattern.match(path)
            )
            if len(scoped) != 1:
                raise TransformError(
                    "expected exactly one semantic ASAR entry bundle for %s, found %s"
                    % (rule.name, scoped)
                )
        exact_candidates: list[PatchCandidate] = [
            (path, match.start(), match.end(), None, replacement)
            for path, content in contents.items()
            if _member_matches(rule, path)
            for find, replacement in rule.exact_pairs
            for match in re.finditer(re.escape(find), content)
        ]
        structural_candidates: list[PatchCandidate] = []
        if rule.structural is not None:
            structural_candidates = [
                (path, match.start(), match.end(), match, None)
                for path, content in contents.items()
                if _structural_member_matches(rule, path)
                for match in rule.structural.pattern.finditer(content)
            ]

        candidates = _semantic_candidates(exact_candidates, structural_candidates)
        if len(candidates) != 1:
            locations = [
                (path, start, end, "exact" if match is None else "structural")
                for path, start, end, match, _replacement in candidates
            ]
            raise TransformError(
                "expected exactly one semantic ASAR occurrence of %s, found %s"
                % (rule.name, locations)
            )

        path, start, end, structural_match, exact_replacement = candidates[0]
        if (
            structural_match is not None
            and not allow_structural_fallback
            and not rule.structural_auto
        ):
            raise TransformError(
                "structural fallback disabled for %s at %s; exact pinned anchors are required; "
                "use --allow-structural-fallback only for manual diagnostics"
                % (rule.name, path)
            )
        if structural_match is None:
            replacement = exact_replacement
            if replacement is None:
                raise TransformError("exact candidate without a replacement")
            updated = contents[path][:start] + replacement + contents[path][end:]
            if rule.extension:
                if replacement not in updated:
                    raise TransformError(
                        "patch did not apply %r in %s" % (replacement, path)
                    )
            elif rule.find in updated:
                raise TransformError(
                    "patch did not consume %r in %s" % (rule.find, path)
                )
        else:
            if rule.structural is None:
                raise TransformError("structural candidate without a structural rule")
            replacement = rule.structural.replacement(structural_match)
            if not isinstance(replacement, bytes) or replacement == structural_match.group(0):
                raise TransformError(
                    "structural patch %s produced no change" % rule.structural.name
                )
            original = contents[path]
            updated = original[:start] + replacement + original[end:]
            if rule.extension:
                if replacement not in updated:
                    raise TransformError(
                        "structural patch %s did not apply" % rule.structural.name
                    )
            elif rule.structural.pattern.search(updated):
                raise TransformError(
                    "structural patch %s did not consume its source shape"
                    % rule.structural.name
                )

        contents[path] = updated
        applied.append((rule, path, replacement, structural_match is not None))

    result = _rebuild_asar(blob, header, json_start, json_len, data_offset, contents)
    rebuilt_contents = _packed_contents(result)
    for rule, path, replacement, _used_structural_fallback in applied:
        data = rebuilt_contents.get(path)
        if data is None or replacement not in data:
            raise TransformError("expected replacement is missing: %s" % rule.name)
        if rule.extension and rule.structural is None and data.count(rule.find) != 1:
            raise TransformError("expected anchor exactly once in output: %r" % rule.find)
        if not rule.extension and rule.find in data:
            raise TransformError("expected source shape is still present: %s" % rule.name)
    return result, applied


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


def _updated_integrity(integrity: object, data: bytes) -> dict:
    """Recompute hash/blocks for new member bytes, preserving key order."""
    if not isinstance(integrity, dict):
        raise TransformError("asar member integrity is missing")
    if integrity.get("algorithm") != "SHA256":
        raise TransformError("asar member integrity algorithm is not SHA256")
    block_size = integrity.get("blockSize")
    if type(block_size) is not int or block_size <= 0:
        raise TransformError("asar member integrity blockSize is malformed")
    updated: dict = {}
    for key, value in integrity.items():
        if key == "hash":
            updated[key] = _sha256_hex(data)
        elif key == "blocks":
            updated[key] = _block_hashes(data, block_size)
        else:
            updated[key] = value
    return updated


def _rebuild_asar(
    blob: bytes,
    header: dict,
    json_start: int,
    json_len: int,
    data_offset: int,
    new_contents: dict[str, bytes],
) -> bytes:
    """Rebuild the archive with replaced member bytes.

    Members keep their data order while offsets, sizes, and integrity
    entries are rewritten by splicing only those value spans into the
    original JSON header, so unpacked entries and unknown fields are
    preserved byte for byte. Fail if the on-disk layout is unexpected.
    """
    members = _walk_files(header)
    json_text = blob[json_start : json_start + json_len].decode("utf-8")
    edits: list[tuple[int, int, str]] = []
    payload = bytearray()
    cursor = data_offset
    for path, meta in members:
        if meta.get("unpacked"):
            continue
        start = data_offset + int(meta["offset"])
        size = int(meta["size"])
        if start != cursor:
            raise TransformError("unexpected asar data layout at %s" % path)
        if path not in new_contents:
            raise TransformError("missing rebuilt member %s" % path)
        data = new_contents[path]
        member_start, _member_end = _member_span(json_text, path)
        new_offset = str(len(payload))
        offset_start, offset_end = _value_span_for_key(
            json_text, member_start, "offset"
        )
        if json_text[offset_start:offset_end] != json.dumps(meta["offset"]):
            raise TransformError("unexpected asar offset encoding at %s" % path)
        if new_offset != meta["offset"]:
            edits.append((offset_start, offset_end, json.dumps(new_offset)))
        if len(data) != size:
            size_start, size_end = _value_span_for_key(
                json_text, member_start, "size"
            )
            edits.append((size_start, size_end, json.dumps(len(data))))
        original = _member_bytes(blob, meta, data_offset)
        if data != original:
            try:
                integrity_start, integrity_end = _value_span_for_key(
                    json_text, member_start, "integrity"
                )
            except TransformError as exc:
                raise TransformError(
                    "asar member integrity is missing"
                ) from exc
            updated = _updated_integrity(
                json.loads(json_text[integrity_start:integrity_end]), data
            )
            edits.append(
                (
                    integrity_start,
                    integrity_end,
                    json.dumps(updated, separators=(",", ":")),
                )
            )
        payload.extend(data)
        cursor = start + size

    for start, end, text in sorted(edits, reverse=True):
        json_text = json_text[:start] + text + json_text[end:]
    encoded_json = json_text.encode("utf-8")
    string_payload = struct.pack("<I", len(encoded_json)) + encoded_json + b"\x00"
    pad = (4 - (len(string_payload) % 4)) % 4
    pickle_payload = string_payload + (b"\x00" * pad)
    header_pickle = struct.pack("<I", len(pickle_payload)) + pickle_payload
    header_size_pickle = struct.pack("<I", 4) + struct.pack(
        "<I", len(header_pickle)
    )
    return header_size_pickle + header_pickle + bytes(payload)


def apply_transforms(
    blob: bytes,
    swaps: Iterable[tuple[bytes, bytes]],
    extensions: Iterable[tuple[bytes, bytes]],
) -> tuple[bytes, set[str]]:
    """Apply swap and extension patches, rebuilding the archive as needed.

    Every pattern must occur exactly once across packed members or the
    transform fails closed. Member sizes may change; offsets, sizes, and
    integrity entries are rewritten to match. Returns the rebuilt archive
    and the set of touched member paths.
    """
    swap_list = list(swaps)
    extension_list = list(extensions)
    for find, replace in swap_list + extension_list:
        _validate_patch_pair(find, replace)
    header, json_start, json_len, data_offset = read_asar(blob)
    contents: dict[str, bytes] = {}
    for path, meta in _walk_files(header):
        if meta.get("unpacked"):
            continue
        contents[path] = _member_bytes(blob, meta, data_offset)
    touched: set[str] = set()

    def locate(find: bytes) -> str:
        hits = [
            (path, content.count(find))
            for path, content in contents.items()
            if find in content
        ]
        if len(hits) != 1 or hits[0][1] != 1:
            raise TransformError(
                "expected exactly one ASAR occurrence of %r, found %s"
                % (find, hits)
            )
        return hits[0][0]

    for find, replace in swap_list:
        path = locate(find)
        updated = contents[path].replace(find, replace, 1)
        if find in updated:
            raise TransformError("patch did not consume %r in %s" % (find, path))
        contents[path] = updated
        touched.add(path)
    for find, replace in extension_list:
        path = locate(find)
        updated = contents[path].replace(find, replace, 1)
        if replace not in updated:
            raise TransformError("patch did not apply %r in %s" % (replace, path))
        contents[path] = updated
        touched.add(path)
    if not touched:
        raise TransformError("no ASAR members were patched")
    return (
        _rebuild_asar(blob, header, json_start, json_len, data_offset, contents),
        touched,
    )


def apply_native_frame_patches(
    blob: bytes, *, allow_structural_fallback: bool = False
) -> bytes:
    """Patch packed members and rebuild the archive fail-closed.

    Rules marked structural_auto use a stable path-scoped semantic matcher
    that tolerates minifier churn automatically. Any remaining structural
    rule is retained only for an explicit manual diagnostic invocation.
    """
    result, _applied = _apply_native_frame_rules(
        blob, allow_structural_fallback=allow_structural_fallback
    )

    if WINDOWS_WCO_MARK not in result or MAC_FRAME_MARK not in result:
        raise TransformError("refusing to drop macOS/Windows window chrome")
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


def patch_asar_file(
    path: str, *, allow_structural_fallback: bool = False
) -> list[str]:
    """Patch one ASAR and require explicit approval for manual fallbacks."""
    with open(path, "rb") as handle:
        original = handle.read()
    patched, applied = _apply_native_frame_rules(
        original, allow_structural_fallback=allow_structural_fallback
    )
    if WINDOWS_WCO_MARK not in patched or MAC_FRAME_MARK not in patched:
        raise TransformError("refusing to drop macOS/Windows window chrome")
    fallbacks = [
        "%s in %s" % (rule.name, member_path)
        for rule, member_path, _replacement, used_structural_fallback in applied
        if used_structural_fallback
    ]
    manual_fallbacks = [
        "%s in %s" % (rule.name, member_path)
        for rule, member_path, _replacement, used_structural_fallback in applied
        if used_structural_fallback and not rule.structural_auto
    ]
    if manual_fallbacks and not allow_structural_fallback:
        raise TransformError(
            "structural fallback requires explicit "
            "--allow-structural-fallback: %s" % ", ".join(manual_fallbacks)
        )
    _write_patched_asar(path, patched)
    return fallbacks


def _write_patched_asar(path: str, patched: bytes) -> None:
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
    allow_structural_fallback = False
    if len(args) == 2 and args[0] == "--allow-structural-fallback":
        allow_structural_fallback = True
        args = args[1:]
    if len(args) != 1 or not args[0]:
        sys.stderr.write(
            "usage: patch_electron_native_frame.py [--allow-structural-fallback] /path/to/app.asar\n"
        )
        return 1
    path = args[0]
    try:
        fallbacks = patch_asar_file(
            path, allow_structural_fallback=allow_structural_fallback
        )
        for fallback in fallbacks:
            sys.stderr.write(
                "patch_electron_native_frame: structural fallback: %s\n" % fallback
            )
    except (OSError, TransformError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        sys.stderr.write("patch_electron_native_frame: %s\n" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
