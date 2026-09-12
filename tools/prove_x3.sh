#!/usr/bin/env bash
# Hosted X3 launch proof for the Unofficial Grok Bot Flatpak.
#
# Both X3 architecture jobs call this single script after their
# architecture-specific checksum and build steps, so the fail-closed
# proof stays identical on x86_64 and aarch64.
#
# Chain position: successful validate on main -> X3 -> publish.
# Run from the repository root with build-dir present.
#
# What counts as PASS:
# - a real KDE Plasma plasmashell process on Xvfb under a real D-Bus
#   session,
# - ownership of the real org.kde.StatusNotifierWatcher name proven with
#   GetNameOwner semantics (never mere activatable-list membership, never
#   a provisioned watcher),
# - the Packaged Payload launched through /app/bin/grok-bot-companion
#   staying non-zombie for the full 8-second observation interval,
# - plasmashell still alive after observation.
# Anything else exits nonzero (UNPROVEN or FAILED) so publish never runs.
set -euo pipefail

export DISPLAY=:99
export QT_QPA_PLATFORM=xcb
Xvfb :99 -screen 0 1920x1080x24 >xvfb.log 2>&1 &
XVFB_PID=$!
trap 'kill "${XVFB_PID}" 2>/dev/null || true' EXIT
for i in $(seq 1 30); do
  if [ -S /tmp/.X11-unix/X99 ]; then
    break
  fi
  sleep 1
  if [ "${i}" = 30 ]; then
    echo "X3 launch proof UNPROVEN: Xvfb did not create display :99" >&2
    exit 1
  fi
done
cat > /tmp/x3-inner.sh <<'INNER_EOF'
set -euo pipefail
# Ownership proof: the name must have an owner, not merely appear
# in activatable metadata. Each probe uses GetNameOwner semantics.
watcher_owned() {
  if command -v busctl >/dev/null 2>&1; then
    if busctl --user get-name-owner org.kde.StatusNotifierWatcher >/dev/null 2>&1; then
      return 0
    fi
    if busctl --user call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus GetNameOwner s org.kde.StatusNotifierWatcher >/dev/null 2>&1; then
      return 0
    fi
    return 1
  elif command -v gdbus >/dev/null 2>&1; then
    if gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus --method org.freedesktop.DBus.GetNameOwner org.kde.StatusNotifierWatcher >/dev/null 2>&1; then
      return 0
    fi
    return 1
  elif command -v dbus-send >/dev/null 2>&1; then
    if dbus-send --session --print-reply --dest=org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus.GetNameOwner string:org.kde.StatusNotifierWatcher >/dev/null 2>&1; then
      return 0
    fi
    return 1
  else
    echo "X3 launch proof UNPROVEN: no D-Bus probe (busctl/gdbus/dbus-send) to verify StatusNotifierWatcher ownership" >&2
    return 1
  fi
}
# Activity-manager ownership uses the same GetNameOwner semantics.
# Plasmashell aborts shell load without a running kactivitymanagerd
# (KDE race 466193, no systemd activation under dbus-run-session),
# so the watcher never gains an owner unless this name is owned first.
activity_owned() {
  if command -v busctl >/dev/null 2>&1; then
    if busctl --user get-name-owner org.kde.ActivityManager >/dev/null 2>&1; then
      return 0
    fi
    if busctl --user call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus GetNameOwner s org.kde.ActivityManager >/dev/null 2>&1; then
      return 0
    fi
    return 1
  elif command -v gdbus >/dev/null 2>&1; then
    if gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus --method org.freedesktop.DBus.GetNameOwner org.kde.ActivityManager >/dev/null 2>&1; then
      return 0
    fi
    return 1
  elif command -v dbus-send >/dev/null 2>&1; then
    if dbus-send --session --print-reply --dest=org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus.GetNameOwner string:org.kde.ActivityManager >/dev/null 2>&1; then
      return 0
    fi
    return 1
  else
    echo "X3 launch proof UNPROVEN: no D-Bus probe (busctl/gdbus/dbus-send) to verify ActivityManager ownership" >&2
    return 1
  fi
}
# Zombie-safe liveness: kill -0 alone passes for zombies, so also
# reject Z state via /proc and ps.
companion_alive() {
  local pid=$1
  if ! kill -0 "${pid}" 2>/dev/null; then
    return 1
  fi
  if [ -r "/proc/${pid}/stat" ]; then
    local state
    state="$(awk '{print $3}' "/proc/${pid}/stat" 2>/dev/null || true)"
    if [ "${state}" = "Z" ] || [ -z "${state}" ]; then
      return 1
    fi
  else
    return 1
  fi
  local ps_state
  ps_state="$(ps -o stat= -p "${pid}" 2>/dev/null || true)"
  case "${ps_state}" in
    *Z*|"")
      return 1
      ;;
  esac
  return 0
}
# Full tree cleanup: terminate the launched process group so no
# Flatpak/bwrap descendants leak after observation.
cleanup_group() {
  local pid=$1
  local pgid
  pgid="$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d '[:space:]' || true)"
  if [ -n "${pgid}" ] && [ "${pgid}" != "1" ]; then
    kill -TERM -"${pgid}" 2>/dev/null || true
    sleep 2
    kill -KILL -"${pgid}" 2>/dev/null || true
  else
    kill -TERM "${pid}" 2>/dev/null || true
    sleep 2
    kill -KILL "${pid}" 2>/dev/null || true
  fi
}
# Race 466193: start the real activity manager before plasmashell and
# wait for org.kde.ActivityManager ownership; otherwise plasmashell
# aborts shell load and the watcher never gains an owner. The daemon
# binary is not on PATH (it lives under /usr/lib/<arch>/libexec), so
# resolve it from the authoritative D-Bus service file, which is
# architecture-independent.
KAMD_BIN="$(command -v kactivitymanagerd 2>/dev/null || true)"
if [ -z "${KAMD_BIN}" ]; then
  KAMD_BIN="$(awk '/^Exec=/{sub(/^Exec=/, ""); print $1; exit}' /usr/share/dbus-1/services/org.kde.ActivityManager.service 2>/dev/null || true)"
fi
if [ -z "${KAMD_BIN}" ] || [ ! -x "${KAMD_BIN}" ]; then
  echo "X3 launch proof UNPROVEN: kactivitymanagerd binary not found (tried PATH and org.kde.ActivityManager.service Exec)" >&2
  exit 1
fi
"${KAMD_BIN}" >kactivitymanagerd.log 2>&1 &
ACTIVITY_PID=$!
PLASMA_PID=""
trap 'kill "${ACTIVITY_PID}" 2>/dev/null || true; kill "${PLASMA_PID}" 2>/dev/null || true' EXIT
if ! kill -0 "${ACTIVITY_PID}" 2>/dev/null; then
  echo "X3 launch proof UNPROVEN: kactivitymanagerd failed to start" >&2
  cat kactivitymanagerd.log || true
  exit 1
fi
ACTIVITY_OK=0
for i in $(seq 1 30); do
  if activity_owned; then
    ACTIVITY_OK=1
    break
  fi
  if ! kill -0 "${ACTIVITY_PID}" 2>/dev/null; then
    echo "X3 launch proof UNPROVEN: kactivitymanagerd exited before ActivityManager was owned" >&2
    cat kactivitymanagerd.log || true
    exit 1
  fi
  sleep 2
done
if [ "${ACTIVITY_OK}" != 1 ]; then
  echo "X3 launch proof UNPROVEN: org.kde.ActivityManager has no owner after kactivitymanagerd start" >&2
  cat kactivitymanagerd.log || true
  exit 1
fi
echo "ActivityManager owned on the session bus (real kactivitymanagerd)"
plasmashell --no-respawn >plasmashell.log 2>&1 &
PLASMA_PID=$!
if ! kill -0 "${PLASMA_PID}" 2>/dev/null; then
  echo "X3 launch proof UNPROVEN: plasmashell failed to start" >&2
  cat kactivitymanagerd.log || true
  cat plasmashell.log || true
  exit 1
fi
WATCHER_OK=0
for i in $(seq 1 60); do
  if watcher_owned; then
    WATCHER_OK=1
    break
  fi
  if ! kill -0 "${PLASMA_PID}" 2>/dev/null; then
    echo "X3 launch proof UNPROVEN: plasmashell exited before the watcher was owned" >&2
    cat kactivitymanagerd.log || true
    cat plasmashell.log || true
    exit 1
  fi
  sleep 2
done
if [ "${WATCHER_OK}" != 1 ]; then
  echo "X3 launch proof UNPROVEN: org.kde.StatusNotifierWatcher has no owner after plasmashell start" >&2
  cat kactivitymanagerd.log || true
  cat plasmashell.log || true
  exit 1
fi
echo "StatusNotifierWatcher owned on the session bus (real plasmashell)"
# X3: companion is a long-running tray. PASS only with owned
# org.kde.StatusNotifierWatcher plus the companion staying
# non-zombie for the full interval; exit 0 is not expected.
prove_x3() {
  set +e
  setsid flatpak-builder --run build-dir io.github.viniciosrab.GrokBot.yml /app/bin/grok-bot-companion >x3-launch.log 2>&1 &
  local pid=$!
  local alive=1
  for i in $(seq 1 8); do
    sleep 1
    if ! companion_alive "${pid}"; then
      alive=0
      break
    fi
  done
  if [ "${alive}" = 1 ] && companion_alive "${pid}"; then
    cleanup_group "${pid}"
    wait "${pid}" 2>/dev/null || true
    set -e
    cat x3-launch.log
    echo "X3 launch proof: PASS — watcher-verified companion stayed up (tray process)"
    return 0
  fi
  cleanup_group "${pid}"
  wait "${pid}"
  local rc=$?
  set -e
  cat x3-launch.log
  echo "X3 launch proof FAILED: companion exited ${rc}" >&2
  return 1
}
prove_x3
if ! kill -0 "${PLASMA_PID}" 2>/dev/null; then
  echo "X3 launch proof FAILED: plasmashell died during observation" >&2
  cat kactivitymanagerd.log || true
  cat plasmashell.log || true
  exit 1
fi
if ! kill -0 "${ACTIVITY_PID}" 2>/dev/null; then
  echo "X3 launch proof FAILED: kactivitymanagerd died during observation" >&2
  cat kactivitymanagerd.log || true
  cat plasmashell.log || true
  exit 1
fi
INNER_EOF
dbus-run-session -- bash /tmp/x3-inner.sh
