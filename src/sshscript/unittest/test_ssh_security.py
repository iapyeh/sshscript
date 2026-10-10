"""Credential-free tests for SSH trust boundaries and remote I/O."""

import asyncio
from io import StringIO, BytesIO
from pathlib import Path
import socket
import tempfile
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
from errorutils import SSHScriptException


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

    def test_local_mode_reads_root_trust_file(self):
        created = []

        def factory():
            client = self.Client()
            created.append(client)
            return client

        parent = Session()
        parent.set(known_hosts='local')
        self.addCleanup(parent.close)
        with patch.object(session_module.paramiko, 'SSHClient', factory), \
             patch.object(parent, '_read_known_hosts', return_value=paramiko.HostKeys()) as read_keys:
            child = parent.connect('example.test', username='user', ssh_config=False)

        read_keys.assert_called_once()
        self.assertFalse(created[0].loaded_system_keys)
        self.assertIsNone(created[0].policy)
        child.close()

    def test_auto_add_policy_requires_explicit_opt_in(self):
        client = self.Client()
        parent = Session()
        parent.set(known_hosts='local')
        self.addCleanup(parent.close)
        policy = paramiko.AutoAddPolicy()
        with patch.object(
            session_module.paramiko,
            'SSHClient',
            return_value=client,
        ), patch.object(parent, '_read_known_hosts', return_value=paramiko.HostKeys()):
            child = parent.connect(
                'example.test',
                ssh_config=False,
                username='user',
                policy=policy,
            )

        self.assertIs(client.policy, policy)
        child.close()


class KnownHostsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = paramiko.RSAKey.generate(1024)
        cls.stale = paramiko.RSAKey.generate(1024)

    def setUp(self):
        self.folder = self.enterContext(tempfile.TemporaryDirectory())
        self.local = Session()
        self.addCleanup(self.local.close)
        self.path = Path(self.folder) / 'known_hosts'
        self.path.write_text('')
        self.local.known_hosts_path = self.path
        self.host1 = self.remote(self.local, 'host1')
        self.host2 = self.remote(self.host1, 'host2')

    def remote(self, parent, host):
        session = Session(parent)
        self.addCleanup(session.close)
        session._host = host
        session._client = Mock()
        session._client.get_transport.return_value.is_active.return_value = True
        session._sftp = Mock()
        session._sftp.normalize.return_value = '/home/login'
        self.trust(session, '')
        return session

    def line(self, host, key=None):
        key = key or self.good
        return f'{host} {key.get_name()} {key.get_base64()}\n'

    def trust(self, source, data):
        if source._client is None:
            Path(source.known_hosts_path).write_text(data)
        else:
            source._sftp.open.side_effect = lambda *args: BytesIO(data.encode())

    def loaded(self, strategy='chain', host='host3', port=22):
        client = paramiko.SSHClient()
        self.addCleanup(client.close)
        self.host2._load_connection_host_keys(client, host, port, strategy)
        return client.get_host_keys()

    def test_default_and_settings_validation_path_is_not_inherited(self):
        self.assertEqual(self.local.known_hosts, 'parent')
        self.assertIsNone(self.host1.known_hosts_path)
        self.host1.set(known_hosts='chain', known_hosts_path='/trust/host1')
        child = Session(self.host1)
        self.addCleanup(child.close)
        self.assertEqual(child.known_hosts, 'chain')
        self.assertIsNone(child.known_hosts_path)
        before = child.get()
        for value, exception in [('other', ValueError), (None, TypeError), (1, TypeError)]:
            with self.assertRaises(exception):
                child.set(check=True, known_hosts=value)
            self.assertEqual(child.get(), before)
        for value, exception in [('', ValueError), ('x\x00', ValueError), (b'path', TypeError), (True, TypeError)]:
            with self.assertRaises(exception):
                child.set(check=True, known_hosts_path=value)
            self.assertEqual(child.get(), before)

    def test_nearest_source_wins_and_distant_files_are_not_read(self):
        self.trust(self.local, self.line('host3', self.stale))
        self.trust(self.host1, self.line('host3', self.stale))
        self.trust(self.host2, self.line('host3'))
        self.assertEqual(self.loaded()['host3']['ssh-rsa'], self.good)
        self.host1._sftp.open.assert_not_called()
        self.host2._sftp.open.assert_called_once_with('/home/login/.ssh/known_hosts', 'rb')
        self.host2._client.exec_command.assert_not_called()

    def test_chain_falls_back_only_when_target_is_absent(self):
        self.trust(self.host2, self.line('unrelated'))
        self.trust(self.host1, self.line('host3', self.stale))
        self.trust(self.local, self.line('host3'))
        self.assertEqual(self.loaded()['host3']['ssh-rsa'], self.stale)
        self.trust(self.host1, '')
        self.assertEqual(self.loaded()['host3']['ssh-rsa'], self.good)

    def test_parent_has_no_fallback_and_local_uses_root_path(self):
        self.trust(self.local, self.line('host3'))
        self.assertIsNone(self.loaded('parent').lookup('host3'))
        self.assertEqual(self.loaded('local')['host3']['ssh-rsa'], self.good)
        self.host1._sftp.open.assert_not_called()

    def test_hashed_hostname_nonstandard_port_and_whitespace(self):
        identity = '[host3]:2222'
        hashed = paramiko.HostKeys.hash_host(identity)
        text = self.line(hashed).replace(' ', '  \t') + '# comment\n'
        self.trust(self.host2, text)
        self.assertEqual(self.loaded(host='host3', port=2222)[identity]['ssh-rsa'], self.good)
        self.assertIsNone(self.loaded().lookup('host3'))

    def test_read_failures_stop_chain_and_identify_source(self):
        self.trust(self.local, self.line('host3'))
        for error in (PermissionError(), FileNotFoundError(), OSError('read failed')):
            self.host2._sftp.open.side_effect = error
            with self.assertRaisesRegex(SSHScriptException, 'Unable to read known_hosts on host2'):
                self.loaded()
            self.host1._sftp.open.assert_not_called()
        self.host2._sftp.open.side_effect = lambda *args: BytesIO(b'\xff')
        with self.assertRaisesRegex(SSHScriptException, 'UnicodeDecodeError'):
            self.loaded()

    def test_parse_errors_stop_even_when_an_earlier_line_matches(self):
        invalid = ['broken', 'host3 ssh-rsa !!!', 'host3 unsupported AAAA',
                   '@revoked ' + self.line('host3'), self.line('*.example'),
                   self.line('|1|bad|bad')]
        for line in invalid:
            self.trust(self.host2, self.line('host3') + line)
            with self.assertRaisesRegex(SSHScriptException, 'host2: .*line 2'):
                self.loaded()
            self.host1._sftp.open.assert_not_called()

    def test_explicit_remote_path_uses_sftp_without_shell(self):
        path = '/trust/key\"; injected-command; #'
        self.host2.known_hosts_path = path
        self.trust(self.host2, self.line('host3'))
        self.loaded()
        self.host2._sftp.open.assert_called_once_with(path, 'rb')
        self.host2._client.exec_command.assert_not_called()

    def handshake(self, policy=None, strategy=None, pkey_path=None):
        client_socket, server_socket = socket.socketpair()
        self.addCleanup(client_socket.close)
        self.addCleanup(server_socket.close)
        server = paramiko.Transport(server_socket)
        server.add_server_key(self.good)
        event = threading.Event()

        class AuthServer(paramiko.ServerInterface):
            def check_auth_password(self, username, password):
                return paramiko.AUTH_SUCCESSFUL

        server.start_server(event=event, server=AuthServer())
        def close_server():
            server.close()
            server.join(3)
            self.assertFalse(server.is_alive())
        self.addCleanup(close_server)
        self.host2._client.get_transport.return_value.open_channel.return_value = client_socket
        options = dict(username='fixture', password='fixture', ssh_config=False,
                       look_for_keys=False, allow_agent=False, timeout=3,
                       banner_timeout=3, auth_timeout=3)
        if policy is not None:
            options['policy'] = policy
        if strategy is not None:
            options['known_hosts'] = strategy
        if pkey_path is not None:
            options['pkey_path'] = pkey_path
        child = self.host2.connect('host3', **options)
        self.addCleanup(child.close)
        return child

    def test_real_handshake_parent_default_and_chain_override_snapshot(self):
        self.host2.known_hosts = 'parent'
        self.trust(self.host1, self.line('host3'))
        child = self.handshake(strategy='chain')
        self.assertTrue(child.connected)
        self.assertEqual(child.known_hosts, 'parent')
        self.assertEqual(self.host2.known_hosts, 'parent')
        self.assertIsNone(child.known_hosts_path)

    def test_real_handshake_parent_default_accepts_near_match(self):
        self.trust(self.host2, self.line('host3'))
        self.trust(self.local, self.line('host3', self.stale))
        self.assertTrue(self.handshake().connected)
        self.host1._sftp.open.assert_not_called()

    def test_real_handshake_near_mismatch_rejects_despite_distant_match_and_autoadd(self):
        self.host2.known_hosts = 'chain'
        self.trust(self.host2, self.line('host3', self.stale))
        self.trust(self.host1, self.line('host3'))
        self.trust(self.local, self.line('host3'))
        with self.assertRaises(paramiko.BadHostKeyException):
            self.handshake(policy=paramiko.AutoAddPolicy())
        self.host1._sftp.open.assert_not_called()
        self.assertEqual(self.host2.subsessions, [])

    def test_real_handshake_parent_does_not_consult_local_match(self):
        self.trust(self.local, self.line('host3'))
        with self.assertRaisesRegex(paramiko.SSHException, 'not found in known_hosts'):
            self.handshake()

    def test_near_record_for_another_algorithm_still_blocks_fallback(self):
        self.host2.known_hosts = 'chain'
        self.trust(self.host2, self.line('host3', paramiko.ECDSAKey.generate()))
        self.trust(self.host1, self.line('host3'))
        with self.assertRaises(paramiko.BadHostKeyException):
            self.handshake(policy=paramiko.AutoAddPolicy())
        self.host1._sftp.open.assert_not_called()

    def test_chain_unknown_rejects_after_all_sources_are_read(self):
        self.host2.known_hosts = 'chain'
        with self.assertRaisesRegex(paramiko.SSHException, 'not found in known_hosts'):
            self.handshake()
        self.host1._sftp.open.assert_called_once()

    def test_missing_local_path_is_an_error_for_parent_and_chain(self):
        self.local.known_hosts_path = Path(self.folder) / 'missing'
        for strategy in ('parent', 'chain', 'local'):
            with self.assertRaisesRegex(SSHScriptException, 'localhost.*FileNotFoundError'):
                self.local._load_connection_host_keys(paramiko.SSHClient(), 'host3', 22, strategy)

    def test_missing_default_local_file_is_an_error_in_every_strategy(self):
        self.local.known_hosts_path = None
        with patch.dict(os.environ, {'HOME': self.folder}):
            for strategy in ('parent', 'chain', 'local'):
                with self.assertRaisesRegex(SSHScriptException, 'localhost.*FileNotFoundError'):
                    self.local.connect('host3', known_hosts=strategy,
                        policy=paramiko.AutoAddPolicy(), ssh_config=False)

    def test_unknown_policy_autoadd_is_in_memory_and_pkey_stays_on_caller(self):
        self.host2.known_hosts = 'chain'
        sentinel_path = '/host2/key'
        with patch.object(self.host2, 'pkey', return_value=self.good) as read_key:
            child = self.handshake(policy=paramiko.AutoAddPolicy(), pkey_path=sentinel_path)
        read_key.assert_called_once_with(sentinel_path)
        self.assertEqual(child._client.get_host_keys()['host3']['ssh-rsa'], self.good)
        self.assertEqual(self.path.read_text(), '')
        for source in (self.host1, self.host2):
            self.assertTrue(all(call.args[1] == 'rb' for call in source._sftp.open.call_args_list))

    def test_invalid_strategy_fails_before_opening_tunnel(self):
        with self.assertRaises(ValueError):
            self.host2.connect('host3', known_hosts='invalid')
        self.host2._client.get_transport.return_value.open_channel.assert_not_called()


class RemoteEnvironmentTests(unittest.TestCase):
    def make_paramiko_channel(self, explicit_environment=None):
        sshchannel = channelssh.SSHChannel.__new__(channelssh.SSHChannel)
        owner = Mock()
        owner.command = ''
        owner.session = Session()
        self.addCleanup(owner.session.close)
        owner.session.host = 'example.test'
        owner._parameters_to_execute = {
            'environment': explicit_environment or {},
        }
        sshchannel.owner = owner
        sshchannel.logger = owner.session.logger
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

            def close(self):
                self.closed = True

        remote_channel = Mock()
        remote_channel.recv_exit_status.return_value = 0
        stdin = Mock()
        stdin.channel = remote_channel
        stdout = Stream(b'out', remote_channel)
        stderr = Stream(b'err', remote_channel)
        client = Mock()
        client.exec_command.return_value = stdin, stdout, stderr
        remote_session = Session()
        self.addCleanup(remote_session.close)
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
        stdin.write.assert_called_once_with('password')
        stdin.flush.assert_called_once_with()
        self.assertTrue(stdout.closed and stderr.closed)
        stdin.close.assert_called_once_with()
        remote_channel.close.assert_called_once_with()
        self.assertTrue(remote_channel.shutdown_write.called)

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

            def close(self):
                self.closed = True

        client = Mock()
        client.exec_command.return_value = (
            stdin,
            Stream(b'host-name\n'),
            Stream(b''),
        )
        remote_session = Session()
        self.addCleanup(remote_session.close)
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
