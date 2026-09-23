"""Real OpenSSH integration tests for the installed SSHScript artifact.

The normal unit suite skips this module.  ``tools/setup_openssh_ci.sh``
provisions a loopback-only server and exports the variables required to enable
it.  No repository credential or external host is used.
"""

from contextlib import suppress
import os
from pathlib import Path
import shlex
import tempfile
import time
import unittest
import uuid

import paramiko

from sshscript import Session


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

    def test_host_key_reject_trust_and_mismatch(self):
        self.known_hosts.write_text("", encoding="utf-8")
        unknown_parent = self._new_parent()
        with self.assertRaises(paramiko.SSHException):
            unknown_parent.connect(
                self.host,
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
                username=self.username,
                port=self.port,
                key_filename=str(self.key_path),
                look_for_keys=False,
                allow_agent=False,
                timeout=5,
                banner_timeout=5,
                auth_timeout=5,
            )

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
        stdout, stderr = remote.exec_command(
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

        stdout, stderr = remote.exec_command(
            "tty",
            shell=False,
            get_pty=False,
            timeout=10,
        )
        self.assertNotEqual(remote.exitcode, 0)
        self.assertIn("not a tty", (str(stdout) + str(stderr)).lower())

        stdout, stderr = remote.exec_command(
            "tty",
            shell=False,
            get_pty=True,
            timeout=10,
        )
        self.assertEqual(remote.exitcode, 0)
        self.assertIn("/dev/pts/", str(stdout) + str(stderr))

        with remote.shell("bash -i", get_pty=True) as console:
            stdout, stderr = console("tty", command_timeout=10)
            self.assertEqual(console.exitcode, 0)
            self.assertIn("/dev/pts/", str(stdout) + str(stderr))

    def test_real_sudo_and_su_password_dialogs(self):
        remote = self._connect()

        with remote.sudo(self.password, get_pty=True) as root_console:
            stdout, stderr = root_console(
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
            stdout, stderr = target_console(
                "whoami",
                command_timeout=15,
            )
            self.assertEqual(target_console.exitcode, 0)
            self.assertRegex(
                str(stdout) + str(stderr),
                rf"(?m)^{self.target_username}\r?$",
            )

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
