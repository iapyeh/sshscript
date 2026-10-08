"""Real OpenSSH integration tests for the installed SSHScript artifact.

The normal unit suite skips this module.  ``tools/setup_openssh_ci.sh``
provisions a loopback-only server and exports the variables required to enable
it.  No repository credential or external host is used.
"""

from contextlib import suppress
import os
import hashlib
from pathlib import Path
import shlex
import tempfile
import time
import unittest
import uuid

import paramiko

from sshscript import Session, CommandTimeoutError


ENABLED = os.environ.get("SSHSCRIPT_OPENSSH_TESTS") == "1"


@unittest.skipUnless(
    ENABLED,
    "set SSHSCRIPT_OPENSSH_TESTS=1 after running setup_openssh_ci.sh",
)
class OpenSSHIntegrationTests(unittest.TestCase):
    """Exercise SSHScript against an ephemeral, real OpenSSH daemon."""

    @classmethod
    def setUpClass(cls):
        names = (
            "SSHSCRIPT_OPENSSH_HOST",
            "SSHSCRIPT_OPENSSH_PORT",
            "SSHSCRIPT_OPENSSH_USER",
            "SSHSCRIPT_OPENSSH_PASSWORD",
            "SSHSCRIPT_OPENSSH_TARGET_USER",
            "SSHSCRIPT_OPENSSH_TARGET_PASSWORD",
            "SSHSCRIPT_OPENSSH_KEY",
            "SSHSCRIPT_OPENSSH_HOME",
            "SSHSCRIPT_OPENSSH_KNOWN_HOSTS",
            "SSHSCRIPT_OPENSSH_TRUSTED_HOSTS",
            "SSHSCRIPT_OPENSSH_MISMATCH_HOSTS",
        )
        missing = [name for name in names if not os.environ.get(name)]
        if missing:
            raise RuntimeError(
                "missing OpenSSH integration environment: "
                + ", ".join(missing)
            )

        cls.host = os.environ["SSHSCRIPT_OPENSSH_HOST"]
        cls.port = int(os.environ["SSHSCRIPT_OPENSSH_PORT"])
        cls.username = os.environ["SSHSCRIPT_OPENSSH_USER"]
        cls.password = os.environ["SSHSCRIPT_OPENSSH_PASSWORD"]
        cls.target_username = os.environ["SSHSCRIPT_OPENSSH_TARGET_USER"]
        cls.target_password = os.environ[
            "SSHSCRIPT_OPENSSH_TARGET_PASSWORD"
        ]
        cls.key_path = Path(os.environ["SSHSCRIPT_OPENSSH_KEY"])
        cls.client_home = Path(os.environ["SSHSCRIPT_OPENSSH_HOME"])
        cls.known_hosts = Path(
            os.environ["SSHSCRIPT_OPENSSH_KNOWN_HOSTS"]
        )
        cls.trusted_hosts = Path(
            os.environ["SSHSCRIPT_OPENSSH_TRUSTED_HOSTS"]
        )
        cls.mismatch_hosts = Path(
            os.environ["SSHSCRIPT_OPENSSH_MISMATCH_HOSTS"]
        )

        for path in (
            cls.key_path,
            cls.known_hosts,
            cls.trusted_hosts,
            cls.mismatch_hosts,
        ):
            if not path.is_file():
                raise RuntimeError(f"missing OpenSSH integration file: {path}")

        cls._original_home = os.environ.get("HOME")
        os.environ["HOME"] = str(cls.client_home)

    @classmethod
    def tearDownClass(cls):
        if cls._original_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = cls._original_home

    def setUp(self):
        self._select_known_hosts(self.trusted_hosts)

    def tearDown(self):
        self._select_known_hosts(self.trusted_hosts)

    def _select_known_hosts(self, source):
        self.known_hosts.parent.mkdir(parents=True, exist_ok=True)
        self.known_hosts.write_bytes(Path(source).read_bytes())
        self.known_hosts.chmod(0o600)

    def _new_parent(self):
        parent = Session()
        self.addCleanup(parent.close, True)
        return parent

    def _connect(self):
        parent = self._new_parent()
        remote = parent.connect(
            self.host,
            ssh_config=False,
            username=self.username,
            port=self.port,
            key_filename=str(self.key_path),
            look_for_keys=False,
            allow_agent=False,
            timeout=5,
            banner_timeout=5,
            auth_timeout=5,
        )
        return remote

    def _remove_remote_tree(self, remote, path):
        with suppress(Exception):
            remote.exec_command(
                "rm -rf -- " + shlex.quote(path),
                shell=True,
                timeout=10,
            )

    def test_managed_short_deadline(self):
        remote = self._connect()
        started = time.monotonic()
        with self.assertRaises(CommandTimeoutError) as caught:
            remote.exec_command(
                ["sh", "-c", "while :; do echo tick; sleep 0.05; done"],
                command_timeout=0.5, stop_timeout=0.2,
            )
        self.assertLess(time.monotonic() - started, 3)
        # The total budget includes channel setup and command startup, so a
        # short deadline may expire before the first output reaches the client.
        self.assertEqual(caught.exception.result.stop_reason, "timeout")
        self.assertEqual(caught.exception.termination_status, "unknown")
        self.assertEqual(remote.exec_command(["printf", "alive"], command_timeout=3).stdout, "alive")

    def test_real_full_duplex_bulk_input_and_eof(self):
        remote = self._connect()
        payload = bytes(range(256)) * 16384 + '中文\r\n'.encode()
        source = (
            'import sys,hashlib; '
            'sys.stdout.buffer.write(b"O"*3145728); sys.stdout.flush(); '
            'sys.stderr.buffer.write(b"E"*3145728); sys.stderr.flush(); '
            'data=sys.stdin.buffer.read(); '
            'print("\\nINPUT:"+hashlib.sha256(data).hexdigest()); '
            'sys.stderr.write("\\nEOF:"+str(len(data))+"\\n")'
        )
        for mode in ('legacy', 'managed'):
            with self.subTest(mode=mode):
                timing = {'timeout': 20} if mode == 'legacy' else {
                    'command_timeout': 20, 'capture_limit': 4 * 1024 * 1024}
                result = remote.exec_command(['python3', '-u', '-c', source],
                                             input=payload, check=True, **timing)
                self.assertEqual(result.stdout, 'O'*3145728 + '\nINPUT:' + hashlib.sha256(payload).hexdigest() + '\n')
                self.assertEqual(result.stderr, 'E'*3145728 + '\nEOF:' + str(len(payload)) + '\n')
                self.assertEqual(result.exitcode, 0)
        for payload in ('', b''):
            self.assertEqual(remote.exec_command(['cat'], input=payload,
                                                command_timeout=5, check=True).stdout, '')

    def test_real_transport_loss_is_not_completion_or_timeout(self):
        remote = self._connect()
        # Supply a finite server-side fallback: a lost transport cannot prove
        # termination, and tests must not leave an indefinite remote command.
        job = remote.start(['sh', '-c', 'echo ready; sleep 2'], timeout=10)
        seen = ''
        for chunk in job.iter_stdout():
            seen += chunk
            if 'ready' in seen:
                break
        remote._client.get_transport().close()
        with self.assertRaises((EOFError, OSError, paramiko.SSHException)) as caught:
            job.wait()
        self.assertNotIsInstance(caught.exception, CommandTimeoutError)
        self.assertIn('ready', job.stdout)
        for worker in (job._worker, job._monitor):
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertTrue(job._channel.closed)
        with self.assertRaises(BrokenPipeError):
            remote.exec_command(['printf', 'must-not-run-locally'])

    def test_real_nested_ssh_closes_child_and_preserves_parent(self):
        parent = self._connect()
        with parent.connect(self.host, username=self.username, port=self.port,
                            ssh_config=False, key_filename=str(self.key_path),
                            look_for_keys=False, allow_agent=False, timeout=5,
                            banner_timeout=5, auth_timeout=5) as nested:
            transport = nested._client.get_transport()
            result = nested.exec_command(['printf', 'nested'], command_timeout=5, check=True)
            self.assertEqual(result.stdout, 'nested')
            self.assertEqual(result.host, self.host)
        transport.join(2)
        self.assertFalse(transport.is_alive())
        self.assertTrue(nested.closed)
        self.assertEqual(parent.exec_command(['printf', 'parent'], command_timeout=5).stdout, 'parent')

    def test_real_proxyjump_authentication_host_keys_and_cleanup(self):
        with tempfile.TemporaryDirectory(prefix='sshscript-jump-config-') as folder:
            config = Path(folder) / 'config'
            config.write_text(
                'Host jump\n'
                f' HostName {self.host}\n User {self.username}\n Port {self.port}\n'
                f' IdentityFile "{self.key_path}"\n'
                f' UserKnownHostsFile "{self.known_hosts}"\n'
                ' IdentitiesOnly yes\n'
                'Host target\n'
                f' HostName {self.host}\n User {self.username}\n Port {self.port}\n'
                ' ProxyJump jump\n')
            parent = self._new_parent()
            with parent.connect('target', ssh_config=config, key_filename=str(self.key_path),
                                look_for_keys=False, allow_agent=False, timeout=5,
                                banner_timeout=5, auth_timeout=5) as remote:
                proxy = remote._sock
                transport = remote._client.get_transport()
                self.assertEqual(remote.exec_command(['printf', 'jump'], command_timeout=5).stdout, 'jump')
            transport.join(2)
            self.assertFalse(transport.is_alive())
            self.assertIsNotNone(proxy.process.poll())
            self.assertTrue(all(getattr(proxy.process, name).closed
                                for name in ('stdin', 'stdout', 'stderr')))
            self.assertTrue(remote.closed)
            # The jump host also requires a trusted key; a successful target
            # connection must not conceal an unknown key on the proxy hop.
            self.known_hosts.write_text('', encoding='utf-8')
            with self.assertRaises((paramiko.SSHException, EOFError, OSError)):
                parent.connect('target', ssh_config=config, key_filename=str(self.key_path),
                               look_for_keys=False, allow_agent=False, timeout=5,
                               banner_timeout=5, auth_timeout=5)

    def test_managed_timeout_preserves_observed_output(self):
        remote = self._connect()
        started = time.monotonic()
        with self.assertRaises(CommandTimeoutError) as caught:
            with remote.start(
                ["sh", "-c", "while :; do echo tick; sleep 0.05; done"],
                timeout=5, stop_timeout=0.2,
            ) as job:
                # Consume chunks until the marker is complete; iter_stdout()
                # does not promise whole lines. Startup failure must fail.
                observed = ""
                for chunk in job.iter_stdout():
                    observed += chunk
                    if "tick" in observed:
                        break
                self.assertIn("tick", observed)
                job.wait()
        self.assertIn("tick", observed)
        self.assertIn("tick", caught.exception.stdout)
        self.assertEqual(caught.exception.result.stop_reason, "timeout")
        self.assertEqual(caught.exception.termination_status, "unknown")
        self.assertLess(time.monotonic() - started, 8)
        self.assertEqual(remote.exec_command(["printf", "alive"], command_timeout=3).stdout, "alive")

    def test_managed_pty_stop(self):
        remote = self._connect()
        # POSIX terminal job control is exercised against a real OpenSSH PTY.
        with remote.start(
            ["sh", "-c", "trap 'echo flushed; exit 0' INT; echo ready; while :; do sleep 0.1; done"],
            get_pty=True, timeout=10, stop_timeout=2,
        ) as job:
            self.assertIn("ready", next(job.iter_stdout()))
            result = job.stop()
            self.assertEqual(result.termination_status, "confirmed")
            self.assertEqual(result.stop_reason, "cancelled")
            self.assertIn("flushed", result.stdout)
        self.assertEqual(remote.exec_command(["printf", "alive"], command_timeout=3).stdout, "alive")

    def test_host_key_reject_trust_and_mismatch(self):
        self.known_hosts.write_text("", encoding="utf-8")
        unknown_parent = self._new_parent()
        with self.assertRaises(paramiko.SSHException):
            unknown_parent.connect(
                self.host,
                ssh_config=False,
                username=self.username,
                port=self.port,
                key_filename=str(self.key_path),
                look_for_keys=False,
                allow_agent=False,
                timeout=5,
                banner_timeout=5,
                auth_timeout=5,
            )

        self._select_known_hosts(self.trusted_hosts)
        remote = self._connect()
        transport = remote._client.get_transport()
        self.assertTrue(transport.is_active())
        self.assertTrue(
            transport.remote_version.startswith("SSH-2.0-OpenSSH"),
            transport.remote_version,
        )

        remote.close(strict=True)
        self._select_known_hosts(self.mismatch_hosts)
        mismatch_parent = self._new_parent()
        with self.assertRaises(paramiko.BadHostKeyException):
            mismatch_parent.connect(
                self.host,
                ssh_config=False,
                username=self.username,
                port=self.port,
                key_filename=str(self.key_path),
                look_for_keys=False,
                allow_agent=False,
                timeout=5,
                banner_timeout=5,
                auth_timeout=5,
            )

    def test_exact_stdin_and_eof_on_real_ssh(self):
        remote = self._connect()
        command = ["python3", "-c", "import sys; print(sys.stdin.buffer.read().hex())"]
        for payload in (None, '', 'abc', '中文\n', b'\x00\xff\n'):
            for managed in (False, True):
                with self.subTest(payload=payload, managed=managed):
                    timing = {'command_timeout': 5} if managed else {'timeout': 5}
                    result = remote.exec_command(command, input=payload, check=True, **timing)
                    expected = payload.encode('utf-8') if isinstance(payload, str) else payload or b''
                    self.assertEqual(result.stdout, expected.hex() + '\n')

    def test_real_command_stdout_stderr_and_exit_status(self):
        remote = self._connect()
        command = shlex.join(
            (
                "python3",
                "-c",
                (
                    "import sys; "
                    "print('openssh-stdout'); "
                    "print('openssh-stderr', file=sys.stderr); "
                    "raise SystemExit(7)"
                ),
            )
        )
        stdout, stderr, exitcode = remote.exec_command(
            command,
            shell=False,
            timeout=10,
        )

        self.assertEqual(str(stdout), "openssh-stdout\n")
        self.assertEqual(str(stderr), "openssh-stderr\n")
        self.assertEqual(remote.exitcode, 7)

    def test_real_sftp_upload_and_download(self):
        remote = self._connect()
        remote_root = (
            f"/home/{self.username}/"
            f"sshscript-integration-{uuid.uuid4().hex}"
        )
        remote_path = remote_root + "/nested/payload.bin"
        self.addCleanup(self._remove_remote_tree, remote, remote_root)

        with tempfile.TemporaryDirectory(
            prefix="sshscript-openssh-sftp-"
        ) as folder:
            source = Path(folder) / "source.bin"
            downloaded = Path(folder) / "downloaded.bin"
            payload = os.urandom(128 * 1024 + 17)
            source.write_bytes(payload)

            uploaded = remote.upload(
                source,
                remote_path,
                makedirs=True,
                overwrite=False,
            )
            self.assertEqual(uploaded[1], remote_path)
            with self.assertRaises(FileExistsError):
                remote.upload(
                    source,
                    remote_path,
                    overwrite=False,
                )

            downloaded_result = remote.download(remote_path, downloaded)
            self.assertEqual(downloaded_result, (remote_path, str(downloaded)))
            self.assertEqual(downloaded.read_bytes(), payload)

    def test_real_non_pty_and_pty_commands(self):
        remote = self._connect()

        stdout, stderr, exitcode = remote.exec_command(
            "tty",
            shell=False,
            get_pty=False,
            timeout=10,
        )
        self.assertNotEqual(remote.exitcode, 0)
        self.assertIn("not a tty", (str(stdout) + str(stderr)).lower())

        stdout, stderr, exitcode = remote.exec_command(
            "tty",
            shell=False,
            get_pty=True,
            timeout=10,
        )
        self.assertEqual(remote.exitcode, 0)
        self.assertIn("/dev/pts/", str(stdout) + str(stderr))

        with remote.shell("bash -i", get_pty=True) as console:
            stdout, stderr, exitcode = console("tty", command_timeout=10)
            self.assertEqual(console.exitcode, 0)
            self.assertIn("/dev/pts/", str(stdout) + str(stderr))

    def test_real_sudo_and_su_password_dialogs(self):
        remote = self._connect()

        with remote.sudo(self.password, get_pty=True) as root_console:
            stdout, stderr, exitcode = root_console(
                "whoami",
                command_timeout=15,
            )
            self.assertEqual(root_console.exitcode, 0)
            self.assertRegex(
                str(stdout) + str(stderr),
                r"(?m)^root\r?$",
            )

        with remote.su(
            self.target_username,
            self.target_password,
            get_pty=True,
        ) as target_console:
            stdout, stderr, exitcode = target_console(
                "whoami",
                command_timeout=15,
            )
            self.assertEqual(target_console.exitcode, 0)
            self.assertRegex(
                str(stdout) + str(stderr),
                rf"(?m)^{self.target_username}\r?$",
            )

    def test_close_rejects_active_remote_console_and_parent_close(self):
        remote = self._connect()
        with remote.shell('bash -i', get_pty=True) as console:
            for owner in (remote, remote.parent):
                for strict in (False, True):
                    with self.assertRaisesRegex(RuntimeError, 'console context is active'):
                        owner.close(strict=strict)
                    self.assertFalse(owner.closed)
            self.assertTrue(remote.connected)
            console('printf still-active', check=True)
            self.assertIn('still-active', str(console.stdout))
        self.assertTrue(remote.close(strict=True))
        self.assertTrue(remote.close(strict=True))
        self.assertFalse(remote.parent.closed)
        with self.assertRaises(RuntimeError):
            remote.exec_command(['true'])

    def test_real_expect_and_command_timeouts(self):
        remote = self._connect()

        with remote.shell("bash -i", get_pty=True) as console:
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                console.expect(
                    "SSHSCRIPT_OUTPUT_THAT_WILL_NEVER_EXIST",
                    timeout=0.25,
                )
            self.assertLess(time.monotonic() - started, 2)

        remote = self._connect()
        with remote.shell("bash -i", get_pty=True) as console:
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                console("sleep 2", command_timeout=0.25)
            self.assertLess(time.monotonic() - started, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
