"""Exact stdin data and deliberate Enter keys have different public contracts."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import test_command_job as fixtures
import sshscript


PAYLOADS = (None, '', 'abc', 'abc\n', '\n', 'a\n\n', '中文\r\n',
            b'', b'abc', b'\x00\xff\r\n')
READ_STDIN = 'import sys; print(sys.stdin.buffer.read().hex())'


def stdin_request(server, channel, command):
    """Feed actual SSH bytes and EOF into a subprocess, without newline rewriting."""
    def execute():
        try:
            payload = bytearray()
            while data := channel.recv(8192):
                payload.extend(data)
            process = subprocess.Popen(command.decode(), shell=True, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True)
            server.processes.append(process)
            out, err = process.communicate(bytes(payload), timeout=5)
            if out:
                channel.sendall(out)
            if err:
                channel.sendall_stderr(err)
            channel.send_exit_status(process.returncode)
            channel.shutdown_write()
        except (OSError, EOFError):
            pass
        finally:
            channel.close()
    worker = threading.Thread(target=execute, daemon=True)
    server.workers.append(worker)
    worker.start()
    return True


class StdinContractTests(unittest.TestCase):
    local = fixtures.CommandJobTests.local
    remote = fixtures.CommandJobTests.remote

    def test_exact_stdin_on_local_ssh_and_managed_paths(self):
        with patch.object(fixtures.Server, 'check_channel_exec_request', stdin_request):
            for backend, session in (('local', self.local()), ('ssh', self.remote())):
                for mode in ('legacy', 'managed', 'start'):
                    for payload in PAYLOADS:
                        with self.subTest(backend=backend, mode=mode, payload=payload):
                            command = [sys.executable, '-u', '-c', READ_STDIN]
                            if mode == 'start':
                                with session.start(command, input=payload, timeout=5, check=True) as job:
                                    result = job.wait()
                            else:
                                timing = {'timeout': 5} if mode == 'legacy' else {'command_timeout': 5}
                                # None preserves legacy local stdin inheritance.
                                # Give that child a deterministic EOF source;
                                # empty str/bytes exercise SSHScript-owned EOF.
                                no_input = {'stdin': subprocess.DEVNULL} if backend == 'local' and mode == 'legacy' and payload is None else {}
                                result = session.exec_command(command, input=payload, check=True,
                                                              **timing, **no_input)
                            expected = payload.encode('utf-8') if isinstance(payload, str) else payload or b''
                            self.assertEqual(result.stdout, expected.hex() + '\n')
                            self.assertEqual(result.exitcode, 0)

    def test_dollar_argv_stdin_is_data(self):
        namespace = sshscript.run_script(
            'result = $(command, input=payload, check=True)\n',
            {'command': [sys.executable, '-c', READ_STDIN], 'payload': '中文'})
        self.assertEqual(namespace['result'].stdout, '中文'.encode().hex() + '\n')

    def interaction_fixture(self, folder):
        script = Path(folder) / 'dialog.py'
        record = Path(folder) / 'received.jsonl'
        script.write_text(r'''import json, sys
with open(sys.argv[1], 'w', encoding='utf-8') as record:
    while True:
        print('QUESTION>', end='', flush=True)
        data = sys.stdin.buffer.readline()
        if not data or data == b'quit\n':
            break
        record.write(json.dumps(data.hex()) + '\n')
        record.flush()
        print('RECEIVED:' + data.hex(), flush=True)
''')
        return shlex.join([sys.executable, '-u', str(script), str(record)]), record

    def test_shell_commands_raw_text_and_interactive_lines(self):
        for get_pty in (False, True):
            with self.subTest(get_pty=get_pty), tempfile.TemporaryDirectory(prefix='sshscript-dialog-') as tmp:
                command, record = self.interaction_fixture(tmp)
                session = self.local()
                with session.shell('bash', get_pty=get_pty) as shell:
                    self.assertEqual(shell('printf before', check=True).stdout, 'before')
                    with shell.enter(command, prompt='QUESTION>', exit='quit') as program:
                        program.expect('QUESTION>', timeout=3)
                        program.send('原始')
                        # Raw send must leave readline waiting: no implicit Enter.
                        self.assertIsNone(program.expect('RECEIVED:', timeout=.1, silent=True))
                        self.assertEqual(record.read_text(), '')
                        self.assertEqual(program.input('', timeout=3), 'prompt')
                        self.assertEqual(program.input('answer', timeout=3), 'prompt')
                        self.assertEqual(program.input('', timeout=3), 'prompt')
                        # Preserve the caller's newline and append one Enter.
                        program.input('two-lines\n', timeout=3)
                        # Existing aliases remain compatible inside enter().
                        program('legacy', timeout=3)
                    self.assertEqual(shell('printf after', check=True).stdout, 'after')
                actual = [bytes.fromhex(json.loads(line)) for line in record.read_text().splitlines()]
                self.assertEqual(actual, ['原始\n'.encode(), b'answer\n', b'\n',
                                          b'two-lines\n', b'\n', b'legacy\n'])

    def test_dollar_shell_and_explicit_interactive_input(self):
        with tempfile.TemporaryDirectory(prefix='sshscript-spy-dialog-') as tmp:
            command, record = self.interaction_fixture(tmp)
            namespace = sshscript.run_script(
                'with $.shell("bash", get_pty=False):\n'
                '    before = $printf before\n'
                '    with $.enter(command, prompt="QUESTION>", exit="quit"):\n'
                '        $.expect("QUESTION>", timeout=3)\n'
                '        $.send("partial")\n'
                '        state = $.input("-answer", timeout=3)\n'
                '        $legacy\n'
                '    after = $printf after\n', {'command': command})
            self.assertEqual(namespace['before'].stdout, 'before')
            self.assertEqual(namespace['after'].stdout, 'after')
            self.assertEqual(namespace['state'], 'prompt')
            actual = [bytes.fromhex(json.loads(line)) for line in record.read_text().splitlines()]
            self.assertEqual(actual, [b'partial-answer\n', b'legacy\n'])


if __name__ == '__main__':
    unittest.main()
