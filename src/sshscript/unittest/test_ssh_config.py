"""Config resolution uses only disposable config files and fake SSH clients."""
from pathlib import Path
import os
import shlex
import tempfile
import unittest
from unittest.mock import Mock, patch
import paramiko
from cryptography.hazmat.primitives import serialization

from session import Session
from sessionsettings import execution_defaults


class SSHConfigTests(unittest.TestCase):
    def setUp(self):
        # These tests isolate config/policy forwarding from host-file I/O.
        self.enterContext(execution_defaults(known_hosts_source='local'))
        self.read_keys = self.enterContext(patch.object(
            Session, '_read_known_hosts', return_value=paramiko.HostKeys()))
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'config'
        self.path.write_text('''Host production
    HostName 10.0.1.20
    User deploy
    Port 2222
    IdentityFile ~/.ssh/key-%r-%p
Host *
    Port 22
''')

    def resolve(self, **kwargs):
        return Session.resolve_connection('production', ssh_config=self.path, **kwargs)

    def test_alias_and_explicit_overrides_precede_token_expansion(self):
        result = self.resolve(username='override', port=22)
        self.assertEqual(result['hostname'], '10.0.1.20')
        self.assertEqual(result['username'], 'override')
        self.assertEqual(result['port'], 22)
        self.assertEqual(result['key_filename'], [os.path.expanduser('~/.ssh/key-override-22')])
        self.assertEqual(self.resolve()['port'], 2222)

    def test_explicit_key_wins(self):
        key = object()
        result = self.resolve(pkey=key)
        self.assertIs(result['pkey'], key)
        self.assertNotIn('key_filename', result)
        self.assertEqual(self.resolve(key_filename='my-key')['key_filename'], 'my-key')

    def test_user_host_and_wildcard_defaults(self):
        result = Session.resolve_connection('override@production', ssh_config=self.path)
        self.assertEqual(result['username'], 'override')
        other = Session.resolve_connection('other', ssh_config=self.path)
        self.assertEqual(other['hostname'], 'other')
        self.assertEqual(other['port'], 22)

    def test_missing_explicit_config_fails_and_opt_out_does_not_read(self):
        with self.assertRaises(FileNotFoundError):
            Session.resolve_connection('host', ssh_config=self.path.with_name('absent'))
        with patch('sshconfig.open', side_effect=AssertionError('read config')):
            result = Session.resolve_connection('host', ssh_config=False)
        self.assertEqual(result['port'], 22)

    def test_default_config_is_optional(self):
        with patch('sshconfig.os.path.expanduser', return_value=str(self.path)):
            result = Session.resolve_connection('production')
        self.assertEqual(result['hostname'], '10.0.1.20')
        with patch('sshconfig.open', side_effect=FileNotFoundError):
            self.assertEqual(Session.resolve_connection('host')['hostname'], 'host')

    def test_proxycommand_expands_after_overrides_without_launching(self):
        self.path.write_text('Host production\n HostName target\n ProxyCommand nc %h %p %r %%\n')
        with patch('subprocess.Popen', side_effect=AssertionError('started proxy')):
            result = self.resolve(username='user', port=2022)
        self.assertEqual(result['proxy_command'], 'nc target 2022 user %')
        self.assertEqual(self.resolve(proxy_command='custom %h')['proxy_command'], 'custom %h')
        self.assertNotIn('proxy_command', self.resolve(proxy_command=None))

    def test_jump_chain_is_quoted_and_preserves_config_and_host_key_checking(self):
        self.path.write_text('Host production\n HostName 2001:db8::1\n Port 2222\n ProxyJump first,user@[::1]:2200\n')
        result = self.resolve()
        args = shlex.split(result['proxy_command'])
        self.assertEqual(args[0], 'ssh')
        self.assertEqual(args[args.index('-F') + 1], str(self.path))
        self.assertEqual(args[args.index('-W') + 1], '[2001:db8::1]:2222')
        self.assertEqual(args[args.index('-J') + 1], 'first')
        self.assertEqual(args[-1], '::1')
        self.assertIn('StrictHostKeyChecking=yes', args)
        self.assertIn('BatchMode=yes', args)
        self.assertEqual(args[args.index('-p') + 1], '2200')
        self.assertEqual(args[args.index('-l') + 1], 'user')

    def test_conflicting_proxies_require_an_explicit_choice(self):
        self.path.write_text('Host *\n ProxyJump hop\n ProxyCommand nc %h %p\n')
        with self.assertRaisesRegex(ValueError, 'cannot both'):
            self.resolve()
        self.assertEqual(self.resolve(proxy_command='nc target 22')['proxy_command'], 'nc target 22')

    def test_unsupported_directives_are_diagnosed_without_execution(self):
        for directive in ('Match exec "touch sentinel"', 'Include other', 'CanonicalizeHostname yes'):
            self.path.write_text(directive + '\n')
            with patch('subprocess.Popen', side_effect=AssertionError('executed Match')):
                with self.assertRaises(NotImplementedError):
                    self.resolve()
        self.path.write_text('Host *\n IdentityAgent /tmp/agent\n')
        with self.assertWarnsRegex(UserWarning, 'identityagent'):
            self.resolve()

    def test_connect_passes_resolved_settings_to_paramiko(self):
        client = Mock()
        parent = Session()
        self.addCleanup(parent.close)
        with patch('session.paramiko.SSHClient', return_value=client):
            remote = parent.connect('production', ssh_config=self.path, port=22)
        client.connect.assert_called_once_with('10.0.1.20', username='deploy', password=None, port=22,
                                              key_filename=[os.path.expanduser('~/.ssh/key-deploy-22')])
        self.assertEqual(remote.host, '10.0.1.20')
        self.read_keys.assert_called_once()
        client.load_system_host_keys.assert_not_called()
        client.set_missing_host_key_policy.assert_not_called()

    def test_nested_connection_does_not_read_local_config(self):
        parent = Session()
        parent._client = Mock()
        self.addCleanup(parent.close)
        with patch('sshconfig.open', side_effect=AssertionError('read local config')), \
             patch('session.paramiko.SSHClient', return_value=Mock()):
            child = parent.connect('nested', username='user')
        self.assertEqual(child.host, 'nested')
        parent._client.get_transport.return_value.open_channel.assert_called_once_with(
            'direct-tcpip', ('nested', 22), (None, None))

    def test_policy_precedence_and_nested_snapshot(self):
        parent = Session()
        self.addCleanup(parent.close)
        inherited = paramiko.AutoAddPolicy()
        override = paramiko.RejectPolicy()
        parent.set(missing_host_key_policy=inherited)
        clients = [Mock() for _ in range(5)]
        with patch('session.paramiko.SSHClient', side_effect=clients):
            remote = parent.connect('first', ssh_config=False)
            overridden = parent.connect('override', missing_host_key_policy=override, ssh_config=False)
            defaulted = parent.connect('default', missing_host_key_policy=None, ssh_config=False)
            parent.missing_host_key_policy = None
            remote.connect('nested')
            parent.connect('later', ssh_config=False)
        clients[0].set_missing_host_key_policy.assert_called_once_with(inherited)
        clients[1].set_missing_host_key_policy.assert_called_once_with(override)
        clients[2].set_missing_host_key_policy.assert_not_called()
        clients[3].set_missing_host_key_policy.assert_called_once_with(inherited)
        clients[4].set_missing_host_key_policy.assert_not_called()
        self.assertIs(remote.missing_host_key_policy, inherited)
        self.assertIs(overridden.missing_host_key_policy, inherited)
        self.assertIs(defaulted.missing_host_key_policy, inherited)

    def test_policy_class_and_invalid_zero(self):
        parent = Session()
        self.addCleanup(parent.close)
        parent.missing_host_key_policy = paramiko.AutoAddPolicy
        client = Mock()
        with patch('session.paramiko.SSHClient', return_value=client):
            parent.connect('first', ssh_config=False)
        client.set_missing_host_key_policy.assert_called_once_with(paramiko.AutoAddPolicy)
        with patch('session.paramiko.SSHClient') as create:
            with self.assertRaises(TypeError):
                parent.connect('invalid', missing_host_key_policy=0, ssh_config=False)
            create.assert_not_called()

    def test_hostname_keyword_and_explicit_username_never_become_password(self):
        parent = Session()
        self.addCleanup(parent.close)
        client = Mock()
        with patch('session.paramiko.SSHClient', return_value=client):
            parent.connect(hostname='alice@production', username='bob', ssh_config=self.path)
        self.assertEqual(client.connect.call_args.args, ('10.0.1.20',))
        self.assertEqual(client.connect.call_args.kwargs['username'], 'bob')
        self.assertIsNone(client.connect.call_args.kwargs['password'])
        self.assertEqual(self.resolve(username='bob')['username'], 'bob')
        with self.assertRaises(TypeError):
            parent.connect('production', 'bob')

    def test_unknown_and_removed_options_fail_before_io_with_suggestions(self):
        parent = Session()
        self.addCleanup(parent.close)
        for name in ('proxyCommand', 'proxyJump', 'pkey_path', 'key_path', 'policy', 'known_hosts'):
            with self.subTest(name=name), patch('sshconfig.open') as read, \
                 patch('session.paramiko.SSHClient') as create:
                with self.assertRaisesRegex(TypeError, name):
                    parent.connect('production', **{name: 'synthetic-value'})
                read.assert_not_called()
                create.assert_not_called()
        with patch('sshconfig._PARAMIKO_OPTIONS', frozenset()):
            with self.assertRaisesRegex(TypeError, 'auth_strategy'):
                parent.connect('production', auth_strategy=object())

    def test_parent_key_decryption_uses_passphrase_then_password(self):
        parent = Session()
        self.addCleanup(parent.close)
        key = paramiko.RSAKey.generate(1024)
        path = self.path.with_name('encrypted-rsa')
        # OpenSSH is the normal ssh-keygen format; avoid backend-specific legacy
        # encrypted PEM decoding behavior in this argument-forwarding regression.
        path.write_bytes(key.key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
            serialization.BestAvailableEncryption(b'fixture-passphrase')))
        for credentials in ({'passphrase': 'fixture-passphrase', 'password': 'login-value'},
                            {'password': 'fixture-passphrase'}):
            with self.subTest(credentials=list(credentials)):
                client = Mock()
                with patch('session.paramiko.SSHClient', return_value=client):
                    parent.connect('production', parent_key_filename=path,
                                   ssh_config=False, **credentials)
                actual = client.connect.call_args.kwargs
                self.assertEqual(actual['pkey'].get_fingerprint(), key.get_fingerprint())
                self.assertNotIn('key_filename', actual)
                self.assertEqual(actual['password'], credentials['password'])
        with patch('session.paramiko.SSHClient') as create:
            with self.assertRaises((paramiko.SSHException, ValueError)):
                parent.connect('production', parent_key_filename=path,
                               passphrase='incorrect', ssh_config=False)
            create.assert_not_called()

    def test_key_and_socket_conflicts_fail_before_key_or_transport_io(self):
        parent = Session()
        self.addCleanup(parent.close)
        for options in ({'pkey': object()}, {'key_filename': ['local-key']}):
            with patch.object(parent, 'pkey') as load:
                with self.assertRaisesRegex(ValueError, 'parent_key_filename'):
                    parent.connect('production', parent_key_filename='unused',
                                   ssh_config=False, **options)
                load.assert_not_called()
        with patch.object(parent, 'pkey') as load:
            with self.assertRaisesRegex(ValueError, 'sock'):
                parent.connect('production', sock=object(), proxy_command='unused',
                               parent_key_filename='unused', ssh_config=False)
            load.assert_not_called()
        parent._client = Mock()
        with patch.object(parent, 'pkey') as load:
            with self.assertRaisesRegex(ValueError, 'sock'):
                parent.connect('production', sock=object(), parent_key_filename='unused',
                               ssh_config=False)
            load.assert_not_called()
        parent._client.get_transport.return_value.open_channel.assert_not_called()
        with self.assertRaisesRegex(TypeError, 'ssh_config'):
            Session.resolve_connection('production', ssh_config=True)


if __name__ == '__main__':
    unittest.main()
