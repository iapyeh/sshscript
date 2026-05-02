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

import tokenize,re
from io import StringIO

try:
    from .errorutils import  SSHScriptException, dumpScript
except ImportError:
    from errorutils import SSHScriptException, dumpScript


## before 3.12 , no tokenize.FSTRING_START
try:
    tokenize.FSTRING_START
except AttributeError:
    has_fstring = False
    double_braces = re.compile(r'{{.*?}}')
else:
    has_fstring = True

def is_fstring(token):
    try:
        return token.type == tokenize.FSTRING_START
    except AttributeError:
        return token.type == tokenize.STRING and token.string.lower().startswith(('f"', "f'"))
def is_dollar(token):
    ## before v3.12, '$' is ERRORTOKEN
    return (token.type in (tokenize.OP,tokenize.ERRORTOKEN)) and token.string == '$'

def seek_non_space_prevtoken(tokens,i):
    ## before v3.12, for "with $", the space between "with" and "$" , becomes an extra "ERRORTOKEN"
    while i > 0:
       i -= 1 
       if tokens[i].string != ' ': return tokens[i]

def convert(code):
    def convertDollar(code):
        code = code.replace('$.','_c.')
        return code
    def convertFstringAfterV12(tokens,i,endCol,chunk):
        ## add space
        chunk.append(' ' * (tokens[i].start[1] - endCol))
        endCol = tokens[i].end[1]
        while i < len(tokens):
            token = tokens[i]            
            endCol = token.end[1]
            if token.type == tokenize.FSTRING_START:
                chunk.append(token.string) # starting quote, aka, f'
            elif token.type == tokenize.FSTRING_END:
                chunk.append(token.string) # ending quote
                i += 1 ## move i to exclude the ending quote
                break
            elif token.type == tokenize.OP and token.string=='{':
                content = [] ## without "{" and "}"
                i += 1 ## skip "{"
                while i < len(tokens):
                    token = tokens[i]
                    space = token.start[1] - endCol
                    if space: content.append(' ' * space)
                    endCol = token.end[1]
                    if token.type == tokenize.OP and token.string=='}':
                        ## skip "}"
                        break
                    content.append(token.string)
                    i += 1
                ## todo: replace $ in content
                dollarReplacedContent = convertDollar(''.join(content))
                chunk.append('{%s}' % dollarReplacedContent)
            else:
                ## 如果這裡出現{,},必然是{{,}}
                chunk.append(token.string.replace('{','{{').replace('}','}}'))
            i += 1
        ## return the new position of token
        return i,endCol

    def convertFstringBeforeV12(tokens,i,endCol,chunk):
        ## add space
        chunk.append(' ' * (tokens[i].start[1] - endCol))
        endCol = tokens[i].end[1]

        items = {}
        def replacer(m):
            key = f'--{len(items)}--'
            items[key] = m.group(0)
            return key
        content = double_braces.sub(replacer,tokens[i].string)
        content = convertDollar(content)
        for k, v in items.items():
            content = content.replace(k,v)
        chunk.append(content)
        return i+1,endCol
    
    if has_fstring:
        convertFstring = convertFstringAfterV12
    else:
        convertFstring = convertFstringBeforeV12

    def collectTokensUntil(tokens,i,chunk,endCol,*stopTokens):
        stopByToken = None
        
        while i < len(tokens):
            token = tokens[i]
            #print(token)
            doBreak = False
            for stoken in stopTokens:
                if isinstance(stoken,list):
                    if token.type == stoken[0] and token.string==stoken[1]:
                        doBreak = True
                        stopByToken = stoken
                        break
                elif token.type == stoken:
                    doBreak = True
                    stopByToken = stoken
                    break
            if doBreak:
                break
            ## add space
            chunk.append(' ' * (token.start[1] - endCol))
            endCol = token.end[1]        
            chunk.append(token.string)
            i += 1
        return i,endCol,stopByToken

    def collectTokensUntilLastBlock(tokens,i,chunk,endCol,startOp,endOp,suffix):
        startOpCount = 1
        stopOpCount = 0
        while i < len(tokens):
            token = tokens[i]
            
            if  token.type == tokenize.OP and token.string==startOp:
                startOpCount += 1
            elif token.type == tokenize.OP and token.string==endOp:
                stopOpCount += 1  
            elif is_fstring(token):
                ## add space
                chunk.append(' ' * (token.start[1] - endCol))
                endCol = token.end[1]
                i,endCol = convertFstring(tokens,i,endCol,chunk)          
                continue            
            
            
            if startOpCount == stopOpCount:
                ## add space
                chunk.append(' ' * (token.start[1] - endCol))
                endCol = token.end[1]
                chunk.append(suffix)
                break
            ## add space
            chunk.append(' ' * (token.start[1] - endCol))
            endCol = token.end[1]
            chunk.append(token.string)
            i += 1
        return i,endCol
    
    ## converting starts   
    try:
        tokens = list(tokenize.generate_tokens(StringIO(code).readline))
    except tokenize.TokenError as e:
        ## eg.('unexpected EOF in multi-line statement', (77, 0))
        lineno = e.args[1][0]
        dumpScript(code,lineno)
        raise SSHScriptException(e)

    i = 0
    output = []
    chunk = []
    endCol = 0
    while i < len(tokens):
        token = tokens[i]
        prevtoken = seek_non_space_prevtoken(tokens,i)
        nexttoken = tokens[i+1] if i+1 < len(tokens) else None
        nextnexttoken = tokens[i+2] if i+2 < len(tokens) else None
        #print(token)
        #print(chunk)
        #print()
        if token.type == tokenize.ENDMARKER:
            output.append(''.join(chunk))
            chunk = []
            endCol = 0
        
        ## 保留space (x = 1,輸出時不要變成 x=1)
        ## tokenize.NL Stands for "non-significant newlines."
        elif token.type in (tokenize.NEWLINE,tokenize.NL):
            endCol = 0
        else:
            offset = token.start[1] - endCol
            if offset > 0:
                #print('     add space:%s (%s-%s)' % (offset,token.start[1],endCol))
                chunk.append(' ' * (offset))
            endCol = token.end[1]        

        ## convertion starts
        if is_fstring(token):
            i,endCol = convertFstring(tokens,i,endCol,chunk)
        elif is_dollar(token) and\
            nexttoken and\
            (nexttoken.type == tokenize.OP and nexttoken.string=='.'\
             and token.start[1]+1 == nexttoken.start[1]) and\
            (nextnexttoken and nextnexttoken.type == tokenize.NAME ):
            if prevtoken and prevtoken.string == 'with':
                chunk.append('_sshscript_in_context_')
                i += 1
            else:
                ## $.attr => _sshscript_in_context_.attr (以前是轉成_c.attr)
                chunk.append('_sshscript_in_context_')
                i += 1
                endCol = token.end[1]
                if nextnexttoken.type == tokenize.NAME and nextnexttoken.string == 'break':
                    chunk.append('._break')
                    i += 2
                    endCol = nextnexttoken.end[1]
        #### with-dollar ####
        elif is_dollar(token) and\
            prevtoken and\
            prevtoken.type == tokenize.NAME and prevtoken.string == 'with' and\
            nexttoken and\
            nexttoken.type == tokenize.COMMENT and nexttoken.string.startswith('#!'):
            ## with $#!/bin/bash as console: => with _sshscript_in_context_.shell(r""" /bin/bash """) as console:
            ## directly converting to _sshscript_in_context_.shell(, 
            ## no more converting to "withdollar" because it's not necessary
            chunk.append('withdollar(r""" ')
            subtokens = list(tokenize.generate_tokens(StringIO(nexttoken.string[2:]).readline))
            tokens = tokens[:i+2] + subtokens + tokens[i+2:]
            i,endCol,stopByToken = collectTokensUntil(tokens,i+2,chunk,endCol,tokenize.COMMENT,tokenize.NL,tokenize.NEWLINE,[tokenize.OP,':'],[tokenize.NAME,'as'])
            chunk.append(' """)')
        elif is_dollar(token) and\
            prevtoken and\
            prevtoken.type == tokenize.NAME and prevtoken.string == 'with' and\
            nexttoken and\
            is_fstring(nexttoken):
            ## with $f'/bin/shell' as console: => with _sshscript_in_context_.shell(f'/bin/bash') as console:
            chunk.append('withdollar(')
            i,endCol = convertFstring(tokens,i+1,endCol,chunk)
            chunk.append(')')
        elif is_dollar(token) and\
            nexttoken and\
            nexttoken.type == tokenize.OP and nexttoken.string=='(' and\
            prevtoken and\
            prevtoken.type == tokenize.NAME and prevtoken.string == 'with':
            ## with $(f'hostname') => _sshscript_in_context_.shell(f'hostname')
            chunk.append('withdollar(')

            if is_fstring(nextnexttoken):
                i,endCol = convertFstring(tokens,i+2,nexttoken.end[1],chunk)
            else:
                suffix = ''
                i,endCol = collectTokensUntilLastBlock(tokens,i+2,chunk,nexttoken.end[1],'(',')',suffix)
        ## 此條件最鬆，要放在with相關條件的最後一個
        elif is_dollar(token) and\
            prevtoken and (prevtoken.type == tokenize.NAME) and (prevtoken.string == 'with') and\
            nexttoken and (
                (nexttoken.type == tokenize.OP and nexttoken.string==':') or 
                (nexttoken.type == tokenize.NAME and nexttoken.string=='as')
            ):            
            
            chunk.append('_sshscript_in_context_.session')
            if nexttoken.type == tokenize.OP and nexttoken.string==':': 
                ## with $ :, no "as" => with _sshscript_in_context_.session as console:
                i += 1
            elif nexttoken.type == tokenize.NAME and nexttoken.string=='as': 
                ## with $ as console: => with _sshscript_in_context_.session as console:
                i += 1
        ## 此條件最鬆，要放在with相關條件的最後一個
        elif is_dollar(token) and\
            prevtoken and\
            prevtoken.type == tokenize.NAME and prevtoken.string == 'with':
            chunk.append('withdollar(')
            if nexttoken and nexttoken.type == tokenize.STRING: 
                ## with $r'...' as console: => with _sshscript_in_context_.shell(r'...') as console:
                i,endCol,stopByToken = collectTokensUntil(tokens,i+1,chunk,endCol,tokenize.COMMENT,tokenize.NL,tokenize.NEWLINE,[tokenize.OP,':'],[tokenize.NAME,'as'])
            else:
                ## with $/bin/bash as console: => with _sshscript_in_context_.shell(r""" """) as console:
                chunk.append('r""" ')
                i,endCol,stopByToken = collectTokensUntil(tokens,i+1,chunk,endCol,tokenize.COMMENT,tokenize.NL,tokenize.NEWLINE,[tokenize.OP,':'],[tokenize.NAME,'as'])
                chunk.append(' """')
            chunk.append(')')
        #### two dollar ####
        elif is_dollar(token) and\
            nexttoken and\
            is_dollar(nexttoken) and\
            nextnexttoken and\
            is_fstring(nextnexttoken):
            ## $$f'hostname' => _twodollar_(f'hostname'),$$f"hostname" => _twodollar_(f"hostname")
            chunk.append('twodollars(')
            endCol = nexttoken.end[1]
            i,endCol = convertFstring(tokens,i+2,endCol,chunk)
            #chunk.append(',0)')
            chunk.append(')')
        elif is_dollar(token) and\
            nexttoken and\
            is_dollar(nexttoken) and\
            nextnexttoken and\
            nextnexttoken.type == tokenize.STRING:
            ## $$r'\echo' => twodollar(r'\echo')
            chunk.append('twodollars(')
            i,endCol,stopByToken = collectTokensUntil(tokens,i+2,chunk,endCol+1,tokenize.COMMENT,tokenize.NL,tokenize.NEWLINE)
            #chunk.append(',1)')
            chunk.append(')')
        elif is_dollar(token) and\
            nexttoken and\
            is_dollar(nexttoken) and\
            nextnexttoken and\
            nextnexttoken.type == tokenize.NUMBER:
            ## $$1234A => twodollar("1234A")
            chunk.append('twodollars(r"')
            i,endCol,stopByToken = collectTokensUntil(tokens,i+2,chunk,endCol+1,tokenize.COMMENT,tokenize.NL,tokenize.NEWLINE)
            #chunk.append('",1)')
            chunk.append('")')
        elif is_dollar(token) and\
            nexttoken and\
            is_dollar(nexttoken) and\
            nextnexttoken and\
            nextnexttoken.type == tokenize.OP and nextnexttoken.string=='(':
            ## $$(r'\echo') => twodollars(r'\echo')
            suffix = ''

            chunk.append('twodollars(')
            endCol = nextnexttoken.end[1]

            if is_fstring(tokens[i+3]):
                i,endCol = convertFstring(tokens,i+3,endCol,chunk)
                chunk.append(suffix)
            else:
                i,endCol = collectTokensUntilLastBlock(tokens,i+3,chunk,endCol,'(',')',suffix)
        ## this condition must after the above condition which searching for $$(..)
        elif is_dollar(token) and\
            nexttoken and\
            is_dollar(nexttoken) and\
            nextnexttoken and nextnexttoken.type in (tokenize.NAME,tokenize.OP):
            ## $$hostname => twodollar('hostname')
            ## $$/run.sh =>  twodollar('run.sh')
            chunk.append('twodollars(r""" ')
            i,endCol,stopByToken = collectTokensUntil(tokens,i+2,chunk,endCol+1,tokenize.COMMENT,tokenize.NL,tokenize.NEWLINE)
            #chunk.append(' """,1)')
            chunk.append(' """)')
        #### onedollar ####
        elif is_dollar(token) and\
            nexttoken and\
            nexttoken.type == tokenize.OP and nexttoken.string=='(':
            ## $(hostname),$('hostname'),$(f'hostname') => onedollar('hostname',0 | 1)
            ## $(chr(3)) <= send Ctrl+C
            suffix = ''
            ## add space
            endCol = nexttoken.end[1]
            chunk.append('onedollar(')
            if is_fstring(nextnexttoken):
                i,endCol = convertFstring(tokens,i+2,endCol,chunk)
                chunk.append(suffix)
            else:
                i,endCol = collectTokensUntilLastBlock(tokens,i+2,chunk,endCol,'(',')',suffix)
        elif is_dollar(token) and\
            nexttoken and\
            is_fstring(nexttoken):
            ## $f'hostname' => onedollar(f'hostname'),$f"hostname" => _dollar_(f"hostname")
            chunk.append('onedollar(')
            i,endCol = convertFstring(tokens,i+1,endCol,chunk)
            chunk.append(')')
        elif is_dollar(token) and\
            nexttoken and\
            nexttoken.type in (tokenize.NAME, tokenize.OP) and\
            (i==0 or (prevtoken and prevtoken.string!='with')):
            ## $hostname => _dollar_('hostname'), exclude "with $ as"
            ## $/run.sh => _dollar_('/run.sh'), exclude "with $ as"
            chunk.append('onedollar(r""" ')
            i,endCol,stopByToken = collectTokensUntil(tokens,i+1,chunk,endCol,tokenize.COMMENT,tokenize.NEWLINE,tokenize.NL)
            chunk.append(' """)')
        elif is_dollar(token) and\
            nexttoken and\
            nexttoken.type == tokenize.STRING:
            ## $r'\echo' => _dollar_(r'\echo')
            chunk.append('onedollar(')
            i,endCol,stopByToken = collectTokensUntil(tokens,i+1,chunk,endCol,tokenize.COMMENT,tokenize.NEWLINE,tokenize.NL)
            chunk.append(')')
        elif is_dollar(token) and\
            nexttoken and\
            nexttoken.type == tokenize.NUMBER:
            ## $1234a => _dollar_(r'1234a')
            chunk.append('onedollar(r"')
            i,endCol,stopByToken = collectTokensUntil(tokens,i+1,chunk,endCol,tokenize.COMMENT,tokenize.NEWLINE,tokenize.NL)
            chunk.append('")')
        else:
            i += 1
            chunk.append(token.string)
    return ''.join(output)

def unittest():
    import sys,os
    sys.path.insert(0,'dev-parsebytoken')
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
            sources.append((i,source,expected))
    elif sys.argv[1]=='-f':
        p = os.path.join(os.path.dirname(__file__),sys.argv[2])
        if os.path.exists(p):
            with open(p) as fd:
                sources.append((0,fd.read(),None))
    elif len(sys.argv) == 2:
        num2test = [int(x) for x in sys.argv[1].split(',')]
        for i in range(0,40):
            if not (i in num2test): continue
            #dumpToken(script)
            file,source,expected,final= getTestingcase('B',i)
            if source is None:break
            sources.append((i,source,expected))
    #def printWithLineNo(s):
    #    for i,l in enumerate(s.splitlines()):
    #        print(f'{i+1:3d} {l}')
    for (idx,source,expected) in sources:
        print('-' * 40,'source')
        print(source)
        if expected:
            print('-' * 40,'expected')
            print(expected)
        print('-' * 40,'converted')
        converted = convert(source)
        print(converted)
        ## converting non-unittest file
        if not expected: continue
        print('-' * 40)
        ## compare results
        convertedlines = converted.splitlines()
        expectedlines = expected.splitlines()
        errorCount = 0
        for j in range(0,len(convertedlines)):
            try:
                e = expectedlines[j]
            except IndexError:
                e = ''
            try:
                c = convertedlines[j]
            except IndexError:
                c = ''
            if e == c: continue
            errorCount += 1
            print(f'Error: #{1+j}')
            print('Expect:'+e)
            print('   Got:'+c)
        if errorCount == 0:
            print(f'B{idx} pass')
        else:
            print(f'B{idx} failed')
            break

if __name__ == '__main__':
    unittest()
