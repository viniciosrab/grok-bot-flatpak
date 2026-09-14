"""POSIX probe: Show/Quit against a live untracked Electron singleton."""

import os
import socket
import struct
import tempfile
import threading
import unittest

SO_PEERCRED = 17
UCRED_STRUCT = struct.Struct("iii")


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


if __name__ == "__main__":
    unittest.main()
