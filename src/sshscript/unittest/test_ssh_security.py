"""Credential-free tests for SSH trust boundaries and remote I/O."""

import asyncio
from io import StringIO
import os
import threading
import unittest
from unittest.mock import Mock, patch

import paramiko

import channelssh
import dollar as dollar_module
import session as session_module
from dollar import Dollar
from session import Session


class HostKeyPolicyTests(unittest.TestCase):
    class Transport:
        def is_active(self):
            return True

        def set_keepalive(self, interval):
            self.keepalive = interval

    class Client:
        def __init__(self):
            self.transport = HostKeyPolicyTests.Transport()
            self.loaded_system_keys = False
            self.policy = None

        def load_system_host_keys(self):
            self.loaded_system_keys = True

        def set_missing_host_key_policy(self, policy):
            self.policy = policy

        def connect(self, *args, **kwargs):
            self.connect_args = args
            self.connect_kwargs = kwargs

        def get_transport(self):
            return self.transport

        def close(self):
            pass

    def test_secure_host_key_verification_is_the_default(self):
        created = []

        def factory():
            client = self.Client()
            created.append(client)
            return client

        parent = Session()
        self.addCleanup(parent.close)
        with patch.object(session_module.paramiko, 'SSHClient', factory):
            child = parent.connect('example.test', username='user')

        self.assertTrue(created[0].loaded_system_keys)
        self.assertIsNone(created[0].policy)
        child.close()

    def test_auto_add_policy_requires_explicit_opt_in(self):
        client = self.Client()
        parent = Session()
        self.addCleanup(parent.close)
        policy = paramiko.AutoAddPolicy()
        with patch.object(
            session_module.paramiko,
            'SSHClient',
            return_value=client,
        ):
            child = parent.connect(
                'example.test',
                username='user',
                policy=policy,
            )

        self.assertIs(client.policy, policy)
        child.close()


class RemoteEnvironmentTests(unittest.TestCase):
    def make_paramiko_channel(self, explicit_environment=None):
        sshchannel = channelssh.SSHChannel.__new__(channelssh.SSHChannel)
        owner = Mock()
        owner.command = ''
        owner.session.host = 'example.test'
        owner._parameters_to_execute = {
            'environment': explicit_environment or {},
        }
        sshchannel.owner = owner
        sshchannel.wait_for_silent = Mock()
        remote_channel = Mock()
        client = Mock()
        client.get_transport.return_value.open_session.return_value = (
            remote_channel
        )
        sshchannel.client = client
        channelssh.ParamikoChannel(sshchannel, False)
        return remote_channel.update_environment.call_args.args[0]

    def test_process_secrets_are_not_forwarded(self):
        with patch.dict(
            os.environ,
            {'SSHSCRIPT_AUDIT_SECRET': 'must-stay-local'},
            clear=False,
        ):
            environment = self.make_paramiko_channel()

        self.assertNotIn('SSHSCRIPT_AUDIT_SECRET', environment)
        self.assertEqual(environment['TERM'], 'dumb')

    def test_explicit_environment_is_forwarded(self):
        environment = self.make_paramiko_channel(
            {'SSHSCRIPT_EXPLICIT': 'allowed'}
        )
        self.assertEqual(environment['SSHSCRIPT_EXPLICIT'], 'allowed')


class RemotePrivateKeyTests(unittest.TestCase):
    def test_remote_private_key_uses_sftp_not_a_shell(self):
        key_text = 'private-key-data'
        remote_file = StringIO(key_text)
        sftp = Mock()
        sftp.open.return_value = remote_file
        client = Mock()
        transport = client.get_transport.return_value
        transport.is_active.return_value = True

        ssh_session = Session()
        ssh_session._client = client
        ssh_session._sftp = sftp
        self.addCleanup(ssh_session.close)

        sentinel = object()
        with patch.object(
            session_module.paramiko.RSAKey,
            'from_private_key',
            return_value=sentinel,
        ) as parse_key:
            result = ssh_session.pkey('key"; injected-command; #')

        self.assertIs(result, sentinel)
        sftp.open.assert_called_once_with(
            'key"; injected-command; #',
            'rb',
        )
        client.exec_command.assert_not_called()
        self.assertEqual(parse_key.call_args.args[0].read(), key_text)


class RemoteCommandIOTests(unittest.TestCase):
    def test_streams_are_drained_concurrently_and_stdin_gets_eof(self):
        barrier = threading.Barrier(2)

        class Stream:
            def __init__(self, value, channel):
                self.value = value
                self.channel = channel

            def read(self):
                barrier.wait(timeout=2)
                return self.value

        remote_channel = Mock()
        remote_channel.recv_exit_status.return_value = 0
        stdin = Mock()
        stdin.channel = remote_channel
        stdout = Stream(b'out', remote_channel)
        stderr = Stream(b'err', remote_channel)
        client = Mock()
        client.exec_command.return_value = stdin, stdout, stderr
        remote_session = Mock()
        remote_session.host = 'example.test'
        remote_session._client = client

        class CaptureChannel:
            def __init__(self, owner, client, get_pty):
                self.stdout = ''
                self.stderr = ''
                self._exitcode = None

            async def _add_stdout_data(self, value):
                self.stdout += value.decode()

            async def _add_stderr_data(self, value):
                self.stderr += value.decode()

            async def _dump_stdout_err(self):
                pass

            @property
            def exitcode(self):
                return self._exitcode

            def close(self):
                pass

        command = Dollar(
            remote_session,
            'remote-command',
            input='password',
        )
        with patch.object(dollar_module, 'SSHChannel', CaptureChannel):
            asyncio.run(command.exec_by_ssh(False))

        self.assertEqual(command.channel.stdout, 'out')
        self.assertEqual(command.channel.stderr, 'err')
        stdin.write.assert_called_once_with('password\n')
        stdin.flush.assert_called_once_with()
        remote_channel.shutdown_write.assert_called_once_with()

    def test_full_remote_call_waits_for_executor_shutdown(self):
        remote_channel = Mock()
        remote_channel.recv_exit_status.return_value = 0
        stdin = Mock()
        stdin.channel = remote_channel

        class Stream:
            def __init__(self, value):
                self.value = value
                self.channel = remote_channel

            def read(self):
                return self.value

        client = Mock()
        client.exec_command.return_value = (
            stdin,
            Stream(b'host-name\n'),
            Stream(b''),
        )
        remote_session = Mock()
        remote_session.connected = True
        remote_session.host = 'example.test'
        remote_session._client = client

        class CaptureChannel:
            def __init__(self, owner, client, get_pty):
                self.stdout = ''
                self.stderr = ''
                self._exitcode = None
                self.closed = False
                self.failure = None

            async def _add_stdout_data(self, value):
                self.stdout += value.decode()

            async def _add_stderr_data(self, value):
                self.stderr += value.decode()

            async def _dump_stdout_err(self):
                pass

            @property
            def exitcode(self):
                return self._exitcode

            def close(self):
                self.closed = True

            def fail(self, exc):
                self.failure = exc

        command = Dollar(remote_session, 'hostname')
        with patch.object(dollar_module, 'SSHChannel', CaptureChannel):
            result = command()

        self.assertIs(result, command)
        self.assertEqual(command.stdout, 'host-name\n')
        self.assertEqual(command.exitcode, 0)
        self.assertFalse(command.call_thread.is_alive())
        self.assertIsNone(command._worker_exception)


if __name__ == '__main__':
    unittest.main(verbosity=2)
