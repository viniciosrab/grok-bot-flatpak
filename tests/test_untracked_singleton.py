"""POSIX probe: Show/Quit against a live untracked Electron singleton."""

import errno
import os
import select
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SO_PEERCRED = 17
UCRED_STRUCT = struct.Struct("iii")
# Matches companion kUnixSocketConnectTimeoutMs: UI wait stays small.
CONNECT_TIMEOUT_MS = 50
# Blocking connect on a saturated AF_UNIX listener must outlive that bound.
BLOCKING_OBSERVE_MS = 150
TIMING_TOLERANCE_MS = 40


def show_action(child_running, socket_live):
    if child_running or socket_live:
        return "startDetached"
    return "startChild"


def quit_action(child_running, socket_live):
    if child_running:
        return "terminateChildGroup"
    if socket_live:
        return "sigterm_peer"
    return "companion_only"


def saturate_unix_listener(path, backlog=1):
    """Bind a non-accepting AF_UNIX listener and fill its accept queue."""
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(backlog)
    fillers = []
    saturated = False
    for _ in range(256):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.setblocking(False)
        try:
            client.connect(path)
        except OSError as exc:
            fillers.append(client)
            if exc.errno in (
                errno.EAGAIN,
                errno.EWOULDBLOCK,
                errno.EINPROGRESS,
            ):
                saturated = True
                break
            for held in fillers:
                held.close()
            server.close()
            raise
        fillers.append(client)
    return server, fillers, saturated


def nonblocking_connect_unix(path, timeout_ms):
    """POSIX connect used by the companion: never write protocol bytes."""
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.setblocking(False)
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while True:
        try:
            client.connect(path)
            return client
        except OSError as exc:
            err = exc.errno
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            client.close()
            return None
        if err == errno.EINTR:
            continue
        if err in (errno.EINPROGRESS, errno.EALREADY):
            _, writers, _ = select.select([], [client], [client], remaining)
            if not writers:
                client.close()
                return None
            so_error = client.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if so_error != 0:
                client.close()
                return None
            return client
        if err in (errno.EAGAIN, errno.EWOULDBLOCK):
            # Queue is full; the fd is not waiting, so poll the deadline.
            select.select([], [], [], remaining)
            if time.monotonic() >= deadline:
                client.close()
                return None
            continue
        client.close()
        return None


class UntrackedSingletonProbeTests(unittest.TestCase):
    def test_show_quit_decision_with_live_untracked_socket(self):
        self.assertEqual(show_action(False, True), "startDetached")
        self.assertEqual(quit_action(False, True), "sigterm_peer")
        self.assertEqual(show_action(True, True), "startDetached")
        self.assertEqual(quit_action(True, True), "terminateChildGroup")
        self.assertEqual(show_action(False, False), "startChild")
        self.assertEqual(quit_action(False, False), "companion_only")

    def test_so_peercred_returns_listener_pid(self):
        if not hasattr(socket, "AF_UNIX"):
            self.skipTest("AF_UNIX is required")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "SingletonSocket")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(server.close)
            server.bind(path)
            server.listen(1)
            accepted = []

            def accept_one():
                conn, _unused = server.accept()
                accepted.append(conn)

            waiter = threading.Thread(target=accept_one)
            waiter.start()
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(client.close)
            client.connect(path)
            waiter.join(2)
            self.assertFalse(waiter.is_alive())
            self.assertEqual(len(accepted), 1)
            self.addCleanup(accepted[0].close)
            creds = client.getsockopt(socket.SOL_SOCKET, SO_PEERCRED, UCRED_STRUCT.size)
            pid, uid, gid = UCRED_STRUCT.unpack(creds)
            self.assertEqual(pid, os.getpid())
            self.assertGreater(pid, 1)
            self.assertNotEqual(pid, 0)
            self.assertEqual(uid, os.getuid())
            self.assertEqual(gid, os.getgid())
            # Companion must never fall back to executable-name matching.
            self.assertNotEqual(pid, -1)

    def test_blocking_connect_exceeds_deadline_when_backlog_saturated(self):
        if not hasattr(socket, "AF_UNIX"):
            self.skipTest("AF_UNIX is required")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "SingletonSocket")
            server, fillers, saturated = saturate_unix_listener(path)
            self.addCleanup(server.close)
            for held in fillers:
                self.addCleanup(held.close)
            self.assertTrue(saturated)
            started = time.monotonic()
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import socket, sys; "
                    "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); "
                    "s.connect(sys.argv[1])",
                    path,
                ]
            )
            self.addCleanup(lambda: proc.poll() is not None or proc.kill())
            timed_out = False
            try:
                proc.wait(timeout=BLOCKING_OBSERVE_MS / 1000.0)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                proc.wait(timeout=2)
            elapsed_ms = (time.monotonic() - started) * 1000.0
            self.assertTrue(timed_out)
            self.assertGreaterEqual(
                elapsed_ms, BLOCKING_OBSERVE_MS - TIMING_TOLERANCE_MS
            )
            self.assertGreater(elapsed_ms, CONNECT_TIMEOUT_MS)

    def test_nonblocking_connect_stays_within_deadline_when_backlog_saturated(self):
        if not hasattr(socket, "AF_UNIX"):
            self.skipTest("AF_UNIX is required")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "SingletonSocket")
            server, fillers, saturated = saturate_unix_listener(path)
            self.addCleanup(server.close)
            for held in fillers:
                self.addCleanup(held.close)
            self.assertTrue(saturated)
            started = time.monotonic()
            client = nonblocking_connect_unix(path, CONNECT_TIMEOUT_MS)
            elapsed_ms = (time.monotonic() - started) * 1000.0
            if client is not None:
                self.addCleanup(client.close)
            self.assertIsNone(client)
            self.assertGreaterEqual(
                elapsed_ms, CONNECT_TIMEOUT_MS - TIMING_TOLERANCE_MS
            )
            self.assertLessEqual(
                elapsed_ms, CONNECT_TIMEOUT_MS + TIMING_TOLERANCE_MS
            )

    def test_nonblocking_connect_preserves_healthy_peercred(self):
        if not hasattr(socket, "AF_UNIX"):
            self.skipTest("AF_UNIX is required")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "SingletonSocket")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(server.close)
            server.bind(path)
            server.listen(1)
            accepted = []

            def accept_one():
                conn, _unused = server.accept()
                accepted.append(conn)

            waiter = threading.Thread(target=accept_one)
            waiter.start()
            client = nonblocking_connect_unix(path, CONNECT_TIMEOUT_MS)
            waiter.join(2)
            self.assertIsNotNone(client)
            self.addCleanup(client.close)
            self.assertFalse(waiter.is_alive())
            self.assertEqual(len(accepted), 1)
            self.addCleanup(accepted[0].close)
            creds = client.getsockopt(
                socket.SOL_SOCKET, SO_PEERCRED, UCRED_STRUCT.size
            )
            pid, uid, gid = UCRED_STRUCT.unpack(creds)
            self.assertEqual(pid, os.getpid())
            self.assertGreater(pid, 1)
            self.assertEqual(uid, os.getuid())
            self.assertEqual(gid, os.getgid())


if __name__ == "__main__":
    unittest.main()
