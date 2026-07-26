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

try:
    from .errorutils import  dumpScript, SSHScriptException
except ImportError:
    from errorutils import  dumpScript, SSHScriptException

import tokenparser

import __main__

## for setting __main__.SSHScriptExportedNames(called in sshscriptdollar.py)
import session

from dollarchanger import DollarChanger

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
        SSHScriptException: If there's a syntax error in the token script
    '''
    ## convert to token script
    tokenScript = tokenparser.convert(spyscript)
    ## convert to ast tree
    try:
        tree = ast.parse(tokenScript)
    except SyntaxError as e:
        #print(f'file:{script_path}')
        dumpScript(tokenScript,e.lineno)
        raise SSHScriptException(str(e))
    else:
        ## converting to regular python script
        pyTree = DollarChanger().visit(tree)
        ## seems useless
        #pyTree = ast.fix_missing_locations(pyTree)
        pyScript = ast.unparse(pyTree)       
        return pyScript

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