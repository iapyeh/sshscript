"""Bare shell escaped dollars must survive Python tokenization and translation."""
import unittest

import dollarparser
import sshscript


class DollarCommandEscapeTests(unittest.TestCase):
    def test_raw_escaped_dollar_executes_as_literal_without_shell(self):
        for command in (r'$echo \$HOME', r'$echo prefix\$HOME',
                        r'$echo \$HOME \$USER'):
            with self.subTest(command=command):
                source = 'result = ' + command + '\nuses_shell = $.dollar.use_shell\n'
                namespace = sshscript.run_script(source)
                expected = command.removeprefix('$echo ').replace('\\', '')
                self.assertEqual(namespace['result'].stdout.strip(), expected)
                self.assertEqual(namespace['result'].exitcode, 0)
                self.assertFalse(namespace['uses_shell'])

    def test_escaped_dollar_in_shell_keeps_state_and_literal_output(self):
        namespace = sshscript.run_script(
            'with $.shell("bash"):\n'
            '    $VALUE=expanded\n'
            '    literal = $echo \\$VALUE\n'
            '    expanded = $echo "$VALUE"\n')
        self.assertEqual(namespace['literal'].stdout.strip(), '$VALUE')
        self.assertEqual(namespace['expanded'].stdout.strip(), 'expanded')

    def test_python_strings_comments_and_diagnostics_remain_intact(self):
        source = 'text = r"$echo \\$HOME"\n# $echo \\$HOME\nresult = $echo \\$HOME\n'
        namespace = sshscript.run_script(source)
        self.assertEqual(namespace['text'], r'$echo \$HOME')
        self.assertEqual(namespace['result'].stdout.strip(), '$HOME')
        for source in ('value = \\$HOME\n', 'result = $echo \\$HOME\nvalue = \\$HOME\n'):
            with self.subTest(source=source), self.assertRaises(SyntaxError) as caught:
                dollarparser.compile_spy('invalid-python.spy', source)
            self.assertEqual(caught.exception.filename, 'invalid-python.spy')
            self.assertEqual(caught.exception.lineno, len(source.splitlines()))
