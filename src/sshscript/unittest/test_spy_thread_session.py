"""Credential-free regressions for Session inheritance in ``.spy`` threads.

The scenarios mirror ``a.spy`` and ``a2.spy``, but replace Paramiko and the
site-specific proxy, hosts, users, and keys with connected in-memory Session
objects.  Real SSH remains covered by the original manual integration files.
"""

from collections import Counter, defaultdict
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import sshscript
import session as session_module


A_STYLE_SCRIPT = """
import threading

errors = []

def guarded(target, *args):
    try:
        target(*args)
    except BaseException as exc:
        errors.append(exc)

def test_hostname():
    observe("outer-thread", $.session)

with $.connect("outer.example"):
    worker = threading.Thread(
        target=guarded,
        args=(test_hostname,),
        name="a-style-worker",
    )
    worker.start()
    worker.join()

if errors:
    raise errors[0]
"""


A2_STYLE_SCRIPT = """
import threading

errors = []

def guarded(target, *args):
    try:
        target(*args)
    except BaseException as exc:
        errors.append(exc)

def test_hostname_nested(host):
    with $.connect(host):
        observe("nested-thread", $.session)

def test_hostname():
    observe("outer-thread", $.session)
    nested_workers = []
    for host in ("nested-one.example", "nested-two.example"):
        worker = threading.Thread(
            target=guarded,
            args=(test_hostname_nested, host),
            name="nested-" + host,
        )
        nested_workers.append(worker)
        worker.start()
    for worker in nested_workers:
        worker.join()

with $.connect("outer.example"):
    outer_workers = []
    for number in range(2):
        worker = threading.Thread(
            target=guarded,
            args=(test_hostname,),
            name="outer-" + str(number),
        )
        outer_workers.append(worker)
        worker.start()
    for worker in outer_workers:
        worker.join()

if errors:
    raise errors[0]
"""


class _FakeTransport:
    def __init__(self):
        self.active = True

    def is_active(self):
        return self.active


class _FakeSSHClient:
    def __init__(self):
        self.transport = _FakeTransport()

    def get_transport(self):
        return self.transport

    def close(self):
        self.transport.active = False


class SpyThreadSessionTests(unittest.TestCase):
    def setUp(self):
        self.observations = []
        self.connections = []
        self.lock = threading.Lock()

    def fake_connect(
        self,
        parent,
        host,
        username=None,
        password=None,
        port=22,
        policy=None,
        **kwargs,
    ):
        child = session_module.Session(parent)
        child._host = host
        child._port = port
        child._username = username
        child._client = _FakeSSHClient()
        parent.subsessions.append(child)
        with self.lock:
            self.connections.append(
                (threading.current_thread().name, parent, child, host)
            )
        return child

    def observe(self, label, active_session):
        with self.lock:
            self.observations.append(
                (
                    label,
                    threading.current_thread().name,
                    active_session,
                    active_session.parent,
                    active_session.host,
                    bool(active_session.connected),
                )
            )

    def run_spy(self, source):
        with tempfile.TemporaryDirectory(
            prefix="sshscript-thread-session-"
        ) as folder:
            path = Path(folder) / "thread_session.spy"
            path.write_text(source, encoding="utf-8")
            with patch.object(
                session_module.Session,
                "connect",
                autospec=True,
                side_effect=self.fake_connect,
            ):
                result = sshscript.run_file(
                    path,
                    vars={"observe": self.observe},
                )
        self.assertEqual(result, 0)

    def test_connected_session_is_inherited_by_spy_thread(self):
        """Mirror a.spy without requiring its real SSH endpoint."""
        self.run_spy(A_STYLE_SCRIPT)

        self.assertEqual(len(self.connections), 1)
        outer = self.connections[0][2]
        self.assertEqual(len(self.observations), 1)
        label, thread_name, active, parent, host, connected = (
            self.observations[0]
        )
        self.assertEqual(label, "outer-thread")
        self.assertEqual(thread_name, "a-style-worker")
        self.assertIs(active, outer)
        self.assertIs(parent, outer.parent)
        self.assertEqual(host, "outer.example")
        self.assertTrue(connected)

    def test_nested_connections_inherit_parent_in_concurrent_spy_threads(self):
        """Mirror a2.spy, including outer and nested concurrent threads."""
        self.run_spy(A2_STYLE_SCRIPT)

        self.assertEqual(len(self.connections), 5)
        outer = next(
            child
            for _, _, child, host in self.connections
            if host == "outer.example"
        )

        grouped = defaultdict(list)
        for observation in self.observations:
            grouped[observation[0]].append(observation)

        self.assertEqual(len(grouped["outer-thread"]), 2)
        for _, _, active, parent, host, connected in grouped["outer-thread"]:
            self.assertIs(active, outer)
            self.assertIs(parent, outer.parent)
            self.assertEqual(host, "outer.example")
            self.assertTrue(connected)

        self.assertEqual(len(grouped["nested-thread"]), 4)
        nested_hosts = Counter()
        for _, _, active, parent, host, connected in grouped["nested-thread"]:
            self.assertIs(parent, outer)
            self.assertIs(active.parent, outer)
            self.assertTrue(connected)
            nested_hosts[host] += 1
        self.assertEqual(
            nested_hosts,
            Counter(
                {
                    "nested-one.example": 2,
                    "nested-two.example": 2,
                }
            ),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
