#!/bin/sh
# NEGATIVE TEST ONLY: the production companion must fail closed without a
# StatusNotifierWatcher (exit 1 with StatusNotifierWatcher evidence) under
# QT_QPA_PLATFORM=offscreen.
#
# This is NOT X3 launch proof. Positive watcher/tray proof lives
# exclusively in tools/prove_x3.sh plus the automatic hosted x3 workflow.
set -eu

BIN="${1:?usage: check_watcherless.sh <companion-binary>}"
if [ ! -x "${BIN}" ]; then
  echo "companion binary is missing or not executable: ${BIN}" >&2
  exit 1
fi

export QT_QPA_PLATFORM=offscreen

LOG="$(mktemp)"
trap 'rm -f "${LOG}"' EXIT

RUN=""
if command -v dbus-run-session >/dev/null 2>&1; then
  RUN="dbus-run-session --"
fi
BOUNDS=""
if command -v timeout >/dev/null 2>&1; then
  BOUNDS="timeout 60"
fi

set +e
# shellcheck disable=SC2086
${BOUNDS} ${RUN} "${BIN}" >"${LOG}" 2>&1
RC=$?
set -e

cat "${LOG}"
grep -q 'StatusNotifierWatcher' "${LOG}" || {
  echo "watcher gate went silent: no StatusNotifierWatcher evidence" >&2
  exit 1
}
if [ "${RC}" -ne 1 ]; then
  echo "headless launch must fail closed at the watcher gate (exit 1, got ${RC})" >&2
  exit 1
fi
echo "NEGATIVE TEST ONLY: companion rejects a watcherless session with exit 1."
