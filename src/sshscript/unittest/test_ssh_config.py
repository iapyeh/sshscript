"""Config resolution uses only disposable config files and fake SSH clients."""
from pathlib import Path
import os
import shlex
import tempfile
import unittest
from unittest.mock import Mock, patch
import paramiko

from session import Session
from sessionsettings import execution_defaults


class SSHConfigTests(unittest.TestCase):
    def setUp(self):
        # These tests isolate config/policy forwarding from host-file I/O.
        self.enterContext(execution_defaults(known_hosts='local'))
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
        self.assertEqual(result['proxyCommand'], 'nc target 2022 user %')
        self.assertEqual(self.resolve(proxyCommand='custom %h')['proxyCommand'], 'custom %h')
        self.assertNotIn('proxyCommand', self.resolve(proxyCommand=None))

    def test_jump_chain_is_quoted_and_preserves_config_and_host_key_checking(self):
        self.path.write_text('Host production\n HostName 2001:db8::1\n Port 2222\n ProxyJump first,user@[::1]:2200\n')
        result = self.resolve()
        args = shlex.split(result['proxyCommand'])
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
        self.assertEqual(self.resolve(proxyCommand='nc target 22')['proxyCommand'], 'nc target 22')

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
        parent.set(policy=inherited)
        clients = [Mock() for _ in range(5)]
        with patch('session.paramiko.SSHClient', side_effect=clients):
            remote = parent.connect('first', ssh_config=False)
            overridden = parent.connect('override', policy=override, ssh_config=False)
            defaulted = parent.connect('default', policy=None, ssh_config=False)
            parent.policy = None
            remote.connect('nested')
            parent.connect('later', ssh_config=False)
        clients[0].set_missing_host_key_policy.assert_called_once_with(inherited)
        clients[1].set_missing_host_key_policy.assert_called_once_with(override)
        clients[2].set_missing_host_key_policy.assert_not_called()
        clients[3].set_missing_host_key_policy.assert_called_once_with(inherited)
        clients[4].set_missing_host_key_policy.assert_not_called()
        self.assertIs(remote.policy, inherited)
        self.assertIs(overridden.policy, inherited)
        self.assertIs(defaulted.policy, inherited)

    def test_policy_class_and_legacy_zero_override(self):
        parent = Session()
        self.addCleanup(parent.close)
        parent.policy = paramiko.AutoAddPolicy
        clients = [Mock(), Mock()]
        with patch('session.paramiko.SSHClient', side_effect=clients):
            parent.connect('first', ssh_config=False)
            with self.assertWarns(DeprecationWarning):
                parent.connect('legacy', policy=0, ssh_config=False)
        clients[0].set_missing_host_key_policy.assert_called_once_with(paramiko.AutoAddPolicy)
        clients[1].set_missing_host_key_policy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
