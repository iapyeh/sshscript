# Copyright (C) 2022-2026  Hsin Yuan Yeh <iapyeh@gmail.com>
#
# This file is part of Sshscript.
#
# SSHScript is free software; you can redistribute it and/or modify it under the
# terms of the MIT License.
#
# SSHScript is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the MIT License for more details.
#
# You should have received a copy of the MIT License along with SSHScript;
# if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA.
#
'''
2025/2/28   rewrite for working with tokenparser.py
'''
import ast
import builtins
from io import StringIO
import linecache
import sys
import tokenize

if __package__:
    from .errorutils import  dumpScript, SSHScriptException
    from . import tokenparser
    from .dollarchanger import DollarChanger
else:
    from errorutils import  dumpScript, SSHScriptException
    import tokenparser
    from dollarchanger import DollarChanger

def _cache_source(script_path, spyscript):
    """Make the original source available to traceback and inspect."""
    lines = spyscript.splitlines(keepends=True)
    if spyscript and not spyscript.endswith(('\n', '\r')):
        # linecache entries conventionally contain complete physical lines.
        lines[-1] += '\n'
    linecache.cache[script_path] = (
        len(spyscript),
        None,
        lines,
        script_path,
    )


def _source_syntax_error(error, script_path, spyscript):
    """Rebuild a parser error so its displayed text comes from the .spy file."""
    lineno = getattr(error, 'lineno', None) or 1
    requested_lineno = lineno
    source_lines = spyscript.splitlines(keepends=True)
    if source_lines:
        lineno = min(max(lineno, 1), len(source_lines))
    text = source_lines[lineno - 1] if lineno <= len(source_lines) else None
    offset = getattr(error, 'offset', None)
    if text is not None and offset is not None:
        line_end = len(text.rstrip('\r\n')) + 1
        offset = (
            line_end
            if requested_lineno > lineno
            else min(max(offset, 1), line_end)
        )
    details = (
        script_path,
        lineno,
        offset,
        text,
    )
    if sys.version_info >= (3, 10):
        end_lineno = getattr(error, 'end_lineno', None)
        if end_lineno is not None and source_lines:
            end_lineno = min(max(end_lineno, lineno), len(source_lines))
        end_offset = getattr(error, 'end_offset', None)
        if end_lineno == lineno and text is not None and end_offset is not None:
            end_offset = min(max(end_offset, offset or 1), len(text.rstrip('\r\n')) + 1)
        details += (
            end_lineno,
            end_offset,
        )
    return type(error)(getattr(error, 'msg', str(error)), details)


def _translation_syntax_error(error, script_path, spyscript):
    """Turn a transformer failure into a source-located syntax diagnostic."""
    lineno = 1
    current = error.__traceback__
    while current is not None:
        node = current.tb_frame.f_locals.get('node')
        if isinstance(node, ast.AST) and getattr(node, 'lineno', None):
            lineno = node.lineno
        current = current.tb_next
    source_lines = spyscript.splitlines()
    source_line = source_lines[lineno - 1] if lineno <= len(source_lines) else ''
    offset = len(source_line) - len(source_line.lstrip()) + 1
    synthetic = SyntaxError(
        'SSHScript translation failed: %s' % error,
        (script_path, lineno, offset, None),
    )
    return _source_syntax_error(synthetic, script_path, spyscript)


def _token_syntax_error(error, script_path, spyscript):
    """Locate tokenization EOF errors at their unmatched opening delimiter."""
    message, location = error.args
    lineno, offset = location

    if message == 'EOF in multi-line statement':
        opening = {'(': ')', '[': ']', '{': '}'}
        closing = {value: key for key, value in opening.items()}
        delimiters = []
        generator = tokenize.generate_tokens(StringIO(spyscript).readline)
        try:
            for token in generator:
                if token.type != tokenize.OP:
                    continue
                if token.string in opening:
                    delimiters.append(token)
                elif token.string in closing:
                    if delimiters and delimiters[-1].string == closing[token.string]:
                        delimiters.pop()
        except (StopIteration, tokenize.TokenError):
            pass

        if delimiters:
            unmatched = delimiters[-1]
            lineno = unmatched.start[0]
            offset = unmatched.start[1] + 1

    synthetic = SyntaxError(
        message,
        (script_path, lineno, offset, None),
    )
    return _source_syntax_error(synthetic, script_path, spyscript)


def parse(script_path, spyscript):
    """Return a transformed AST whose locations still refer to *spyscript*."""
    _cache_source(script_path, spyscript)
    try:
        token_script = tokenparser.convert(spyscript)
    except tokenize.TokenError as error:
        raise _token_syntax_error(error, script_path, spyscript) from None

    try:
        tree = ast.parse(token_script, filename=script_path)
    except SyntaxError as error:
        raise _source_syntax_error(error, script_path, spyscript) from None

    try:
        py_tree = DollarChanger().visit(tree)
        return ast.fix_missing_locations(py_tree)
    except Exception as error:
        raise _translation_syntax_error(
            error, script_path, spyscript
        ) from error


def compile_spy(script_path, spyscript):
    """Compile dollar syntax while retaining original filename and locations."""
    try:
        return builtins.compile(parse(script_path, spyscript), script_path, 'exec')
    except SyntaxError as error:
        if error.filename == script_path and error.text is None:
            raise _source_syntax_error(error, script_path, spyscript) from None
        raise


def convert(script_path, spyscript):
    '''
    Convert a spy script to a Python script.
    
    This function performs a two-step conversion process:
    1. Converts the spy script to a token script using tokenparser
    2. Converts the token script to a regular Python script using DollarChanger
    
    Args:
        script_path (str): Path to the script file, used for error reporting
        spyscript (str): The spy script content to be converted
        
    Returns:
        str: The converted Python script
        
    Raises:
        SyntaxError: If parsing or translation fails
    '''
    return ast.unparse(parse(script_path, spyscript))

def unittest():
    '''
    Run unit tests for the dollarparser module.
    
    This function tests the conversion process by:
    1. Loading test cases from testingcase module
    2. Converting each test case using the convert function
    3. Comparing the converted output with expected results
    
    Command line options:
        --no-lineno: Suppress line numbers in output
        -f <filename>: Test a specific file
        <numbers>: Test specific test cases by number (comma-separated)
    
    Returns:
        None
    '''
    import sys,os
    from errorutils import dumpScript
    sys.path.insert(0,'dev-parsebytoken')
    
    noLineNumber = False
    if '--no-lineno' in sys.argv:
        noLineNumber = True
        sys.argv.remove('--no-lineno')
    
    try:
        from testingcase import getTestingcase
    except ImportError:
        from .testingcase import getTestingcase
    ## "python3 tokenparser.py 2" would test "2" only
    sources = []
    if len(sys.argv) == 1:
        for i in range(0,40):
            file,source,expected,final = getTestingcase('B',i)
            if source is None: break
            sources.append((file,i,source,final))
    elif sys.argv[1]=='-f':
        p = os.path.join(os.path.dirname(__file__),sys.argv[2])
        if os.path.exists(p):
            with open(p) as fd:
                sources.append((p,0,fd.read(),None))
    elif len(sys.argv) == 2:
        num2test = [int(x) for x in sys.argv[1].split(',')]
        for i in range(0,40):
            if not (i in num2test): continue
            #dumpToken(script)
            file,source,expected,final= getTestingcase('B',i)
            if source is None:break
            sources.append((file,i,source,final))

    for (file,idx,source,final) in sources:
        print('~' * 50,'source')
        if noLineNumber:
            print(source)
        else:
            dumpScript(source)        
        
        newTransformedTokenScript = tokenparser.convert(source)
        print('+' * 50,'token-parser')
        if noLineNumber: print(newTransformedTokenScript)
        else: dumpScript(newTransformedTokenScript)

        if final is not None:
            print('~' * 40,'expected final script')
            if noLineNumber: print(final)
            else: dumpScript(final)

        convertedFinal = convert(file,source)
        print('=' * 40,'final script')
        if noLineNumber: print(convertedFinal)
        else: dumpScript(convertedFinal)

        if not final: continue

        ## comparing 
        convertedlines = convertedFinal.splitlines()
        expectedlines = final.splitlines()
        errorCount = 0
        for j in range(0,max(len(expectedlines),len(convertedlines))):
            try:
                e = expectedlines[j].rstrip()
            except IndexError:
                e = ''
            try:
                c = convertedlines[j].rstrip()
            except IndexError:
                c = ''
            if e == c:
                continue
            errorCount += 1
            print(f'\nError Line: #{1+j}')
            print('Expect:"%s"' % e)
            print('   Got:"%s"' % c)
        if errorCount == 0:
            print(f'B{idx} pass')
        else:
            print(f'B{idx} failed')
            break

if __name__ == '__main__':
    unittest()
