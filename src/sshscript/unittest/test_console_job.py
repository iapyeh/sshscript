"""Console jobs preserve shell state and make unsafe reuse explicit."""
import os
import shlex
import subprocess
import sys
import tempfile
import signal
import time
import test_command_job as ssh_fixtures
import threading
import unittest
from unittest.mock import patch

import sshscript
from commandjob import CommandJob, CommandTimeoutError
from session import Session
from channelutils import SuConsole, SudoConsole, _AuthCommand, _auth_bootstrap
import pwd
import uuid


class ConsoleJobTests(unittest.TestCase):
    def session(self):
        session = Session()
        self.addCleanup(session.close)
        return session

    def python(self, source):
        return shlex.join([sys.executable, '-u', '-c', source])

    def test_protocol_markers_and_prompts_fragmented_without_leaking(self):
        with self.session().shell('bash') as console:
            from consolejob import ConsoleCommandJob
            job = ConsoleCommandJob(console, 'true')
            job._mode = 'running'
            text = 'user-output' + job._prefix + 'BEGIN__:501:123:5.2\n' + job._prompt
            for char in text:
                job._listen(0, char)
            self.assertEqual(job.stdout, 'user-output')
            self.assertIn('BEGIN_PROMPT', job._records)
            self.assertEqual(job._records['BEGIN'][:2], ['501', '123'])

    def test_completed_pipe_and_pty_jobs_preserve_state_and_results(self):
        for pty in (False, True):
            with self.subTest(pty=pty), self.session().shell('bash', get_pty=pty) as console:
                console('export JOB_VALUE=preserved; cd /tmp', check=True)
                command = self.python('import os,sys; print(os.environ["JOB_VALUE"]); print(os.getcwd()); print("error", file=sys.stderr); sys.exit(7)')
                with console.start(command, timeout=3) as job:
                    self.assertIsInstance(job, CommandJob)
                    result = job.wait()
                self.assertIn('preserved', result.stdout)
                self.assertIn('/tmp', result.stdout)
                self.assertIn('error', result.stdout if pty else result.stderr)
                self.assertEqual(result.exitcode, 7)
                self.assertEqual(result.termination_status, 'confirmed')
                self.assertNotIn('__SSJ_', result.stdout + result.stderr)
                self.assertEqual(console('printf alive', check=True).stdout, 'alive')
                self.assertEqual(console.start('printf comment-safe # trailing comment', timeout=3).wait().stdout, 'comment-safe')
                with self.assertRaises(subprocess.CalledProcessError) as caught:
                    with console.start('printf failed; false', check=True, timeout=3) as failing:
                        failing.wait()
                self.assertEqual(caught.exception.result.stdout, 'failed')
                self.assertEqual(caught.exception.returncode, 1)

    def test_stream_stop_exclusivity_and_creator_thread(self):
        with self.session().shell('bash') as console:
            command = self.python('import time; print("ready"); time.sleep(30)')
            with console.start(command, timeout=5, stop_timeout=1) as job:
                observed = ''
                for chunk in job.iter_stdout():
                    observed += chunk
                    if 'ready' in observed:
                        break
                for action in (lambda: console('printf forbidden'), lambda: console.start('true'),
                               lambda: console.send('x'), lambda: console.input('x'),
                               lambda: console.expect('x'), lambda: console.enter('bash'),
                               lambda: console.su('somebody'), lambda: console.sudo(),
                               lambda: console.shell('bash'), console.clear):
                    with self.assertRaisesRegex(RuntimeError, 'active job'):
                        action()
                errors = []
                def other_thread():
                    for action in (job.stop, job.wait, lambda: next(job.iter_stdout()), lambda: console('true')):
                        try:
                            action()
                        except RuntimeError as error:
                            errors.append(str(error))
                thread = threading.Thread(target=other_thread)
                thread.start(); thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(len(errors), 4)
                result = job.stop()
                self.assertEqual(result.stop_reason, 'cancelled')
                self.assertEqual(result.termination_status, 'confirmed')
            self.assertEqual(console('printf restored', check=True).stdout, 'restored')

    def test_deadline_without_consumer_and_context_cleanup(self):
        with self.session().shell('bash') as console:
            with self.assertRaises(CommandTimeoutError) as caught:
                with console.start('sleep 30', timeout=.2, stop_timeout=1) as job:
                    job.wait()
            self.assertEqual(caught.exception.result.stop_reason, 'timeout')
            self.assertEqual(caught.exception.termination_status, 'confirmed')
            self.assertEqual(console('printf restored', check=True).stdout, 'restored')
            with self.assertRaisesRegex(ValueError, 'primary'):
                with console.start('sleep 30', timeout=5, stop_timeout=1):
                    raise ValueError('primary')
            self.assertEqual(console('printf restored', check=True).stdout, 'restored')
        # Leaving the console also stops a job even if its own with block was omitted.
        with self.session().shell('bash') as console:
            job = console.start('sleep 30', timeout=5, stop_timeout=1)
        self.assertTrue(job.done)

    def test_bounded_capture_stderr_fence_and_overflow(self):
        with self.session().shell('bash', get_pty=False) as console:
            command = self.python('import sys; sys.stdout.write("x"*10000000); sys.stderr.write("y"*2000000)')
            with console.start(command, timeout=8, capture_limit=100) as job:
                result = job.wait()
                self.assertEqual(result.stdout, 'x'*100)
                self.assertEqual(result.stderr, 'y'*100)
                self.assertTrue(result.stdout_truncated and result.stderr_truncated)
                with self.assertRaises(BufferError):
                    list(job.iter_stdout())
            self.assertEqual(console('printf alive').stdout, 'alive')

    def test_invalid_commands_and_interactive_start_have_no_side_effects(self):
        with self.session().shell('bash') as console:
            for command in (['true'], '', 'a\nb', 'sleep 1 &', 'sudo hostname',
                            'true; su user', 'nohup sleep 1', 'exec bash'):
                with self.assertRaises((TypeError, ValueError)):
                    console.start(command)
            for options in ({'timeout':True}, {'timeout':0}, {'stop_timeout':0},
                            {'capture_limit':-1}, {'check':'yes'}):
                with self.assertRaises((TypeError, ValueError)):
                    console.start('true', **options)
            # Metacharacters inside argv-style quoted shell arguments are data.
            self.assertEqual(console.start('printf "%s" "&"', timeout=3).wait().stdout, '&')
            command = self.python('import time; print("ready"); time.sleep(30)')
            with console.enter(command, exit=chr(3)) as entered:
                entered.expect('ready', timeout=3)
                with self.assertRaisesRegex(RuntimeError, 'inside enter'):
                    entered.start('true')

    def test_utf8_split_bytes_and_ignored_interrupt(self):
        with self.session().shell('bash') as console:
            command = self.python('import os,time; data="中文".encode(); exec("for byte in data: os.write(1, bytes([byte])); time.sleep(.03)")')
            with console.start(command, timeout=3) as job:
                self.assertEqual(''.join(job.iter_stdout()), '中文')
        with self.session().shell('bash') as console:
            command = self.python('import signal,time; signal.signal(signal.SIGINT, signal.SIG_IGN); print("ready"); time.sleep(3)')
            with self.assertRaises(RuntimeError) as caught:
                with console.start(command, timeout=5, stop_timeout=.2) as job:
                    observed = ''
                    for chunk in job.iter_stdout():
                        observed += chunk
                        if 'ready' in observed:
                            break
                    started = time.monotonic()
                    job.stop()
            self.assertLess(time.monotonic() - started, 1)
            self.assertEqual(caught.exception.result.termination_status, 'unknown')
            with self.assertRaisesRegex(RuntimeError, 'recovery is unconfirmed'):
                console('true')

    def test_pipe_cancellation_and_shell_exit_disable_reuse(self):
        with self.session().shell('bash', get_pty=False) as console:
            with self.assertRaises(RuntimeError) as caught:
                with console.start('sleep 30', timeout=5, stop_timeout=.2) as job:
                    # Wait for dispatch before requesting cancellation.
                    while not job._sent_command:
                        threading.Event().wait(.01)
                    job.stop()
            self.assertEqual(caught.exception.result.termination_status, 'unknown')
            with self.assertRaisesRegex(RuntimeError, 'recovery is unconfirmed'):
                console('true')
        with self.session().shell('bash') as console:
            with self.assertRaises(Exception):
                with console.start('exit', timeout=.3, stop_timeout=.2) as job:
                    job.wait()
            with self.assertRaises(Exception):
                console('true')

    def test_spy_job_context_keeps_console_scope(self):
        namespace = sshscript.run_script(
            'with $.shell("bash"):\n'
            '    $export JOB_VALUE=spy\n'
            '    with $.start("printf $JOB_VALUE", timeout=3) as job:\n'
            '        result = job.wait()\n'
            '    after = $printf alive\n')
        self.assertIsInstance(namespace['job'], CommandJob)
        self.assertEqual(namespace['result'].stdout, 'spy')
        self.assertEqual(namespace['after'].stdout, 'alive')

    def test_su_sudo_protocol_fixture_keeps_nested_identity_and_environment(self):
        # Real Bash channels and UID/PID handshake, but no native privilege change.
        username = pwd.getpwuid(os.getuid()).pw_name
        def simulated(session, user, login, *args, **kwargs):
            token = uuid.uuid4().hex
            return _AuthCommand(_auth_bootstrap(username, False, token), token)
        for method, cls in (('su', SuConsole), ('sudo', SudoConsole)):
            with self.subTest(method=method), patch.object(cls, 'get_command', side_effect=simulated):
                context = self.session().su(username) if method == 'su' else self.session().sudo(username=username)
                with context as console:
                    before = console('printf "%s:%s" "$(id -u)" "$$"', check=True).stdout
                    console('export JOB_VALUE=authenticated', check=True)
                    with console.start('printf "%s:%s:%s" "$(id -u)" "$$" "$JOB_VALUE"', timeout=3) as job:
                        result = job.wait()
                    self.assertEqual(result.stdout, before + ':authenticated')
                    self.assertEqual(console('printf "%s:%s" "$(id -u)" "$$"').stdout, before)

    def test_real_paramiko_pipe_console_job(self):
        # SSH protocol, with actual stdin feeding a persistent remote Bash process.
        def request(server, channel, command):
            def execute():
                process = subprocess.Popen(command.decode(), shell=True, stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           start_new_session=True)
                server.processes.append(process)
                def input_pump():
                    try:
                        while data := channel.recv(65536):
                            process.stdin.write(data); process.stdin.flush()
                    except (OSError, EOFError):
                        pass
                    finally:
                        process.stdin.close()
                def output_pump(stream, send):
                    try:
                        while data := os.read(stream.fileno(), 65536):
                            send(data)
                    except (OSError, EOFError):
                        pass
                pumps = [threading.Thread(target=input_pump, daemon=True),
                         threading.Thread(target=output_pump, args=(process.stdout, channel.sendall), daemon=True),
                         threading.Thread(target=output_pump, args=(process.stderr, channel.sendall_stderr), daemon=True)]
                for thread in pumps:
                    server.workers.append(thread); thread.start()
                process.wait()
                for thread in pumps[1:]:
                    thread.join(1)
                if not channel.closed:
                    channel.send_exit_status(process.returncode); channel.close()
                process.stdout.close(); process.stderr.close()
            thread = threading.Thread(target=execute, daemon=True)
            server.workers.append(thread); thread.start()
            return True
        fixture = ssh_fixtures.CommandJobTests()
        self.addCleanup(fixture.doCleanups)
        with patch.object(ssh_fixtures.Server, 'check_channel_exec_request', request):
            remote = fixture.remote()
            with remote.shell('bash', get_pty=False) as console:
                console('export JOB_VALUE=remote; cd /tmp', check=True)
                with console.start('printf "$JOB_VALUE"; printf error >&2; false', timeout=5) as job:
                    result = job.wait()
                self.assertEqual((result.stdout, result.stderr, result.exitcode), ('remote', 'error', 1))
                self.assertEqual(result.host, 'socketpair.test')
                self.assertEqual(console('printf alive', check=True).stdout, 'alive')
