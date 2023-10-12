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
1. mask python string and long string (StringTransformer)
2. mask $... stuffs. eg. $ls, then mask comments(MaskConmmentTransformer)
    mask $ in advance mask comments, because we don't want to mask $#!/bin/bash as a comment
    when mask comments: do not mask $#!/bin/bash as comment!

3. convert "with $command " to "with withdollar()"
        command will be masked unless it is already a masked token
        if command contains masked-string-token, 
            then the double-quote inside the string will be escaped
   keep "with $.prop"     to "with DOLLARDOT.prop"
        the prop is not be masked.
4. convert $command to onedallar()
        command will be masked into a triple-quoted string unless it is already
        if command contains masked-string-token, 
            then the double-quote inside the string will be escaped
   convert $$command to twodollars()
        command will be masked into a triple-quoted string unless it is already
        if command contains masked-string-token, 
            then the double-quote inside the string will be escaped
   convert $.prop  to DOLLARDOT.prop

5. restore token to string and long string

6. send into Python's ast (DollarChanger)
    convert "with withdollar"
    convert "onedallar()"
    convert "twodollars()" to
REF:
https://deepsource.com/blog/python-asts-by-building-your-own-linter
https://github.com/lark-parser/lark/blob/master/lark/grammars/python.lark
https://regex101.com/

2023/7/6    be compatible with v1.8. tested with sshscriptcare
2023/7/12   remove dependency on "lark", renaming from "larkparser.py" to "sshscriptparser.py"
'''
DEBUG = 0
import os
import copy
import re
import ast
import hashlib
import traceback
try:
    ast.unparse
except AttributeError:
    try:
        import astunparse
    except ImportError:
        print('Python version less than 3.9 require "astunparse" to be installed. Please install it by "pip install astunparse"')
        raise
    else:
        setattr(ast,'unparse', astunparse.unparse)

try:
    from .sshscripterror import  logDebug8, logDebug
except ImportError:
    from sshscripterror import logDebug8, logDebug

if DEBUG:
    def dumpToLines(script,title='',linesep='='):
        if title: print(title)
        print((linesep * 50))
        script = stripLeadingSpace(script)
        for idx,line in enumerate(script.splitlines()):
            print(f'{str(idx).zfill(3)} {line}')
else:
    def dumpToLines(script,title='',linesep='='):
        pass

try:
    from sshscriptdollar import SSHScriptDollar, pstd, pstdSub
except ImportError:
    from .sshscriptdollar import SSHScriptDollar, pstd, pstdSub

import __main__

def stripLeadingSpace(script):
    nonemptyline = ''
    for line in script.splitlines():
        ## get the 1st non-empty line
        if line.strip():
            nonemptyline = line
            break
    ## find prefix
    prefixes = []
    for c in nonemptyline:
        if c in(' ','\t'): prefixes.append(c)
        else: break
    
    ## omit leading prefix
    rows = []
    prefixLen = len(prefixes)
    for line in script.splitlines():
        ## skip "__export__ = [ "line
        if line.lstrip().startswith('__export__=['): continue
        rows.append(line[prefixLen:])
    return os.linesep.join(rows)


curlybracketInLongString = re.compile('(?<!{){((?!{).+?)}(?!})')
curlybracketInDollarCommand = re.compile('@{((?!{).+?)}(?!})')
def curlybracketInLongStringSub(m):
    value = m.group(1)
    value = pstd.sub(pstdSub, value)
    return '{%s}' % value
def curlybracketInDollarCommandSub(m):
    value = m.group(1)
    ## this value without curly brackets, so add curly brackets when calling curlybracketInLongStringSub
    value = curlybracketInLongString.sub(curlybracketInLongStringSub, '{%s}' % value)
    ## remove extra curly brackets
    return '@{%s}' % value[1:-1]

def curlybracketInDollarCommandSubNested(stringTransformer,value):
    def myCurlybracketInDollarCommandSub(m):
        value = m.group(1)
        for token in stringTransformer.tokenPattern.findall(value):
            tokenvalue = stringTransformer.getToken(token)
            ## convert $. to it's python-equivalent
            if token.startswith('f_@@_'):
                tokenvalue = curlybracketInLongString.sub( curlybracketInLongStringSub, tokenvalue)
            elif token.startswith('r_@@_'):
                pass
            else:
                tokenvalue = curlybracketInDollarCommand.sub( curlybracketInDollarCommandSub, tokenvalue)
            ## and escape 3-quotes string inside the string (double quotes only,since it is added into 3-double-quotes)
            #if tokenvalue.startswith('"""') and tokenvalue.endswith('"""'):
            stringTransformer.setToken(token, tokenvalue.replace('"','\\"'))
        ## this value without curly brackets, so add curly brackets when calling curlybracketInLongStringSub
        value = curlybracketInLongString.sub(curlybracketInLongStringSub, '{%s}' % value)
        ## remove extra curly brackets
        return '@{%s}' % value[1:-1]    
    curlybracketInDollarCommand.sub(myCurlybracketInDollarCommandSub,value)
    ## remove extra curly brackets
    return '@{%s}' % value[1:-1]


class StringTransformer(object):
    """
    Mask and restore strings, long strings in spy scripts.
    """
    tokenPattern = re.compile('[fr]?_@@_[a-z0-9]+_')
    tokenOnlyPattern = re.compile('[fr]?_@@_[a-z0-9]+_\Z')
    def genToken(self,value,tokenPrefix=''):
        token = f"{tokenPrefix}_@@_{hashlib.md5(value.encode('utf8')).hexdigest()}{len(self.tokens)}_".lower()
        ## the second flag 0 , means that the token value is not modified
        self.tokens[token] = [value,0]
        return token
    def restore(self, text):
        ## do conversion at most 3 times
        ## since the converted string might contains string-tokens too.
        ## for example $echo @{"hello world"}, would be converted $echo @{_@@_A_token_}, then onedollar(_@@_B_token_)
        maxc = 3 
        while maxc and self.tokenPattern.search(text):
            tokens = self.tokenPattern.findall(text)
            for token in tokens:
                try:
                    value,beenReset = self.tokens[token]
                except KeyError:
                    ## try comment token
                    token = '#' + token
                    value = self.tokens[token][0]
                    ## no matter how, don't convert anything in comment
                    beenReset = 1
                ## only do conversion if value is not been reset
                if beenReset == 0:
                    if token.startswith('f_@@_'):
                        value = curlybracketInLongString.sub(curlybracketInLongStringSub,value)
                text = text.replace(token, value)
                del self.tokens[token]
            maxc -= 1
        return text    
    
    def setToken(self, token, newvalue):
        self.tokens[token][0] = newvalue
        self.tokens[token][1] = 1

    def getToken(self, token):
        return self.tokens[token][0]

    def __init__(self):
        self.tokens = {}

    def mask(self, spyscript):
        self.STRING = re.compile(r'''([ubf]?r?|r[ubf])("(?!"").*?(?<!\\)(\\\\)*?"|'(?!'').*?(?<!\\)(\\\\)*?')''',re.I)
        self.LONG_STRING =  re.compile(r'''([ubf]?r?|r[ubf])(""".*?(?<!\\)(\\\\)*?"""|\'\'\'.*?(?<!\\)(\\\\)*?\'\'\')''', re.I|re.S)
        def long_string(m):
            value = m.group(0)
            if value[:2] in ('r"', "r'") and value[-1] == value[1]:
                ## the "r" of r"string" is included in the value (provided that parser = lalr)
                token = self.genToken(value[1:],tokenPrefix='r')
            elif value[:2] in ('f"', "f'") and value[-1] == value[1]:
                token = self.genToken(value,tokenPrefix='f')
            else:
                token = self.genToken(value)        
            return token
        maskedSpyscript = self.LONG_STRING.sub(long_string, spyscript)

        def a_string(m):
            value = m.group(0)
            if value[:2] in ('r"', "r'") and value[-1] == value[1]:
                ## the "r" of r"string" is included in the value (provided that parser = lalr)
                token = self.genToken(value,tokenPrefix='r')
            elif value[:2] in ('f"', "f'") and value[-1] == value[1]:
                token = self.genToken(value,tokenPrefix='f')
            else:
                token = self.genToken(value)
            return token
        maskedSpyscript = self.STRING.sub(a_string, maskedSpyscript)
        return maskedSpyscript

class MaskConmmentTransformer(StringTransformer):
    """
    mask comments, but before doing it, we need to mask $!#/bin/bash
    """
    grammar = r'''
    COMMENT: /#[^\n]*/
    start : script
    anyothers     .1 : /.+?/ | /\n/    
    dollarrelated_to_end .10: /[^\n]+/
    dollarrelated        .10:  "$" dollarrelated_to_end 
    lowpriority_comment .10: COMMENT
    script: ( dollarrelated | lowpriority_comment | anyothers )*
    '''
    def __init__(self,stringTransformer):
        super().__init__()
        self.rows = []#stringTransformer.rows
        self.tokens = stringTransformer.tokens
    def mask(self,spyscript):
        self.COMMENT = re.compile('#[^\n]*')
        self.DOLLAR_RELATED = re.compile('\$[^\n]+')
        maskedDollarCommands = {}
        def dollarrelated(m):
            value = m.group(0)
            if '#' in value:
                token = f"_key_{hashlib.md5(value.encode('utf8')).hexdigest()}{len(maskedDollarCommands)}_".lower()
                maskedDollarCommands[token] = value
                return token
            else:
                return value
        def lowpriority_comment(m):
            value = m.group(0)
            token = self.genToken(value,tokenPrefix='#')
            return token
        maskedScript = self.DOLLAR_RELATED.sub(dollarrelated,spyscript)
        maskedScript = self.COMMENT.sub(lowpriority_comment,maskedScript)
        ## restore maskedDollarCommands
        for token,value in maskedDollarCommands.items():
            maskedScript = maskedScript.replace(token,value)
        return maskedScript

def assignContextRaw(func):
    ## return a new function that will inherit caller's "localSSHScriptListKey" value
    import types,inspect, threading
    def x(*args,**kw):
        callerLocals = inspect.currentframe().f_back.f_locals
        g = globals()
        g['contextName'] = callerLocals.get('localSSHScriptListKey')
        ## if we can not find the localSSHScriptListKey from caller, then we could  be in a thread
        ## let find it from our parent thread
        if  g['contextName'] is None and hasattr(threading.current_thread().parent,'localSSHScriptListKey'):
            g['contextName'] = threading.current_thread().parent.localSSHScriptListKey
        new_func = types.FunctionType(func.__code__, g, func.__name__, func.__defaults__, func.__closure__)    
        return new_func(*args,**kw)
    return x

class DollarChanger(ast.NodeTransformer):
    tmplLinesAtBeginning = ast.parse('_sshscriptstack_ = threading.current_thread().sshscriptstack').body[0]
    tmplCommand = ast.parse('''
try:
    __b = """cmd"""
    __c = SSHScriptDollar(_sshscriptstack_[-1],__b,locals(),globals(),inWith=False,fr=0)
    __ret = __c(False)
finally:
    _c = __c
    '''.strip())
    ## The reason for weirdness of "__b":
    ## 1. Since the ast.unparse() function does not restore "r-string" to r"...".
    ##    It restores r-string to normal string. So we need to "simulate" it by encode('unicode_escape').decode().
    ## 2. The newline in r'...' is really newline but it is treated as "\\n" by encode('unicode_escape'), so we need
    ##    split the original string into every lines, applying encode('unicode_escape').decode(), then join back
    tmplWithCommand = ast.parse('''
try:
    __b = """cmd"""
    __c = SSHScriptDollar(_sshscriptstack_[-1],__b,locals(),globals(),inWith=True,fr=0)
    __ret = __c(True)
finally:
    _c = __c
with __ret as whatever:
    pass
    '''.strip())  
    tmplWithSuSudoEnter = ast.parse('''
try:
    __b = ''
    __c = SSHScriptDollar(_sshscriptstack_[-1], __b, locals(), globals(), inWith=True, fr=0)
    __ret = __c(True)
finally:
    _c = __c
with __ret as topconsole:
    with topconsole.funcname(args) as subconsole:
        pass
    _c = subconsole
    '''.strip()).body
    tmplLineBelowWithConnect = ast.parse('_sshscriptstack_.append(x)').body[0]  
    ## with-exit would close the session, so, this is pop() not popAndClose()
    tmplLineAfterWithConnect = ast.parse('_sshscriptstack_.pop()').body[0]
    tmplLineForConnect = ast.parse('_new_sshcript = _sshscriptstack_.connectAndAppend("", password="")').body[0]
    tmplLineOfSshscriptstack = ast.parse('_sshscriptstack_').body[0]
    tmplLineForSSHScriptInstance = ast.parse('_sshscriptstack_[-1]').body[0]
    tmplLineAfterClose = ast.parse('_sshscriptstack_.closeAndPop()').body[0]
    tmplLineForNewScope = ast.parse('_sshscriptstack_ = threading.current_thread().sshscriptstack').body[0]
    tmplLinesBlowDef_origin2 = ast.parse('_sshscriptstack_ = threading.current_thread().sshscriptstack(A)').body[0]    
    tmplLinesBlowDef_origin3 = ast.parse("_sshscriptstack_ = threading.current_thread().sshscriptstack.bindGuestStack(sys._getframe(1).f_locals.get('_sshscriptstack_'))").body[0]
    tmplLinesBlowDef = ast.parse("_sshscriptstack_ = sys._getframe(1).f_locals.get('_sshscriptstack_') or threading.current_thread().sshscriptstack").body[0]
    tmplLineAfterDef = ast.parse('_sshscriptstack_()').body[0]
    tmplLineAssignAtBottom = ast.parse('a=_c.stdout, _c.stderr, _c.exitcode').body[0]
    tmplLineAssignStdoutAtBottom = ast.parse('a=_c.stdout').body[0]
    def __init__(self):
        super().__init__()
        self.insideWith = [False]
        self.insideWithitem = False
        self.insideDollarAssign = False
        self.insideSubshell = False
        #self.parent = None       
        self.currentExpr = None
        self.localSSHScriptListKeyStack = ['0']
        ##  initial value is for Module, suppose it is False
        self.containsSSHScriptStack = [False]
        self.currentConsole = []
        self.consoleSerialNo = 0
    def genConsoleName(self):
        self.consoleSerialNo += 1
        return f'_pesudo{self.consoleSerialNo}'
    def generic_visit(self,node):
        newnode = None       
        ## this will greatly make the parsing process slow
        #for child in ast.iter_child_nodes(node):
        #    child.parent = node  
        if hasattr(node,'body') and isinstance(node.body,list):
            ## ast.IfExp (eg. if '$HOME\n' == _c.stdout else 0) has .body, but it is a ast.Constant
            ## so we add the condition "isinstance(node.body,list)"
            try:
                #self.parent = node
                for child in node.body:
                    child.parent = node
                if isinstance(node,ast.If):
                    for child in node.orelse:
                        child.parent = node
            except:
                print('Error %s' % ast.unparse(node))
                print('Error node:',ast.dump(node))
                raise

        if isinstance(node,ast.Expr):
            self.currentExpr = node
        elif isinstance(node,ast.Assign):
            self.currentExpr = node
        elif isinstance(node,ast.Return):
            self.currentExpr = node
        
        
        def walkAndConvert(v):
            if isinstance(v, ast.Attribute):
                if v.value.id == 'DOLLARDOT':
                    converted = pstd.sub(pstdSub,f'$.{v.attr}')
                    v.value.id, v.attr = converted.split('.',1)
            elif isinstance(v, ast.BinOp):
                walkAndConvert(v.left)
                walkAndConvert(v.right)
            elif isinstance(v, ast.Call):
                for arg in v.args:
                    walkAndConvert(arg)
                for k in v.keywords:
                    walkAndConvert(k.value)        
        
        ## increase scopeDepth
        if node.__class__ in (ast.FunctionDef,ast.AsyncFunctionDef):
            
            self.localSSHScriptListKeyStack.append(node.name)

            ## add initial value into self.containsSSHScriptStack for this scope
            self.containsSSHScriptStack.append(False)

        ## check should we set self.containsSSHScript to True
        if isinstance(node, ast.Call) and \
            isinstance(node.func, ast.Attribute) and \
            isinstance(node.func.value, ast.Name) and \
            node.func.value.id == '_sshscript_in_context_':
            self.containsSSHScriptStack[-1] = True

        if isinstance(node, ast.With):
            self.insideWith[-1] = True
        
        if isinstance(node, ast.Assign) and isinstance(node.value,ast.Call) and\
                isinstance(node.value.func,ast.Name) and node.value.func.id in ('onedollar','twodollars'): 
            ## convert stdout, stderr, exitcode = $hostname
            ## convert stdout, stderr, exitcode = $$hostname
            self.insideDollarAssign = True
            node.isDollarAssign = True
        
        ## node modification starts
        if isinstance(node, ast.Module):
            def module_callback(node):
                if self.tmplLinesAtBeginning:
                    node.body.insert(0,copy.deepcopy(self.tmplLinesAtBeginning))
                    ## self.tmplLinesAtBeginning should be added only once
                    ## but this doesn't work because we call self.generic_visit() extrally
                    ## so, this was disabled
                    #self.tmplLinesAtBeginning = None
                return node
            node._callback_ = module_callback
        elif isinstance(node, ast.With): 
            nodeitem = node.items[0]
            if isinstance(nodeitem.context_expr, ast.Call) and \
                isinstance(nodeitem.context_expr.func,ast.Name) and \
                nodeitem.context_expr.func.id=='withdollar':
                self.containsSSHScriptStack[-1] = True                

                ## eg:
                ## with $.sudo 
                ##     with $#!/bin/bash
                #if self.insideSubshell:
                if len(self.currentConsole):
                    ## conver to console.shell()
                    nodeitem.context_expr.func.id = 'shell'
                    nodeitem.context_expr.func = ast.Attribute(value=ast.Name(id=self.currentConsole[-1],ctx=ast.Load()),attr='shell')
                    ## only keep the 1st argument, which is the shell
                    del nodeitem.context_expr.args[1:]
                    if nodeitem.optional_vars is None:
                        nodeitem.optional_vars = ast.Name(id=self.genConsoleName(),ctx=ast.Load())
                    self.currentConsole.append(nodeitem.optional_vars.id)
                    def callback(node):
                        self.currentConsole.pop()
                        return node
                    node._callback_ = callback
                ## eg.
                ##  source:    with $ as sh
                ##  change to: with withdollar('') as sh
                ##  change to: ... (too many lines, see self.tmplWithCommand)
                else:
                    newWithNode = copy.deepcopy(self.tmplWithCommand)
                    newnode = newWithNode
                    trynode = newWithNode.body[0]
                    ## assign cmd
                    command = nodeitem.context_expr.args[0]
                    ## withdollar has one argument only
                    fr = 0
                    if isinstance( command,ast.JoinedStr):
                        for value in command.values:
                            if isinstance(value,ast.Constant):
                                ## restore "$." in f-string if it does not in {} for evaluation
                                ## since this value would put into a f-string again, so we need to escape the escape again
                                value.value = value.value.replace('DOLLARDOT.','$.').replace('\\','\\\\')
                            elif isinstance(value,ast.FormattedValue):
                                ## restore and convert "$." in f-string if it is in {} for evaluation
                                walkAndConvert(value.value)
                        trynode.body[0].value = command
                        fr = 1
                    else:
                        fr = nodeitem.context_expr.args[1].value if len(nodeitem.context_expr.args) > 1 else 0
                        assert isinstance(command,ast.Constant)
                        trynode.body[0].value.value = command.value
                    ## assign inwith
                    trynode.body[1].value.keywords[0].value.value = True
                    ## assign fr
                    trynode.body[1].value.keywords[1].value.value = fr

                    newWithNode.body[1].body = node.body
                    ## change "with $:" to "with $ as _pesudo1:"
                    if nodeitem.optional_vars is None:
                        newWithNode.body[1].items[0].optional_vars = ast.Name(id=self.genConsoleName(),ctx=ast.Load())
                    else:
                        newWithNode.body[1].items[0].optional_vars = nodeitem.optional_vars
                    assert  newWithNode.body[1].items[0].optional_vars is not None
                    ## we should add this console name after the "try" block, right before the "with" block starts
                    ## the reason is that: if not doing so (aka add immediately right here)
                    ## the new console would be applied too early, like this example:
                    ##      $hostname
                    ##      with $f'$.stdout' as console: <- would become console.stdout, but it would _c.stdout
                    ##           pass
                    def addconsole(node):
                        self.currentConsole.append(newWithNode.body[1].items[0].optional_vars.id)
                        return node
                    newWithNode.body[1].items[0]._callback_ = addconsole
                   
                    
                    def callback(node):
                        self.currentConsole.pop()
                        return node
                    newnode._callback_ = callback
         
            elif isinstance(nodeitem.context_expr, ast.Call) and \
                isinstance(nodeitem.context_expr.func,ast.Attribute) and \
                ( (isinstance(nodeitem.context_expr.func.value, ast.Name) and \
                nodeitem.context_expr.func.value.id == '_sshscript_in_context_') or \
                (isinstance(nodeitem.context_expr.func.value, ast.Subscript) and \
                 isinstance(nodeitem.context_expr.func.value.value,ast.Name) and \
                nodeitem.context_expr.func.value.value.id == '_sshscriptstack_') 
                ):
                
                if nodeitem.context_expr.func.attr in ('connect','open'):
                    ## self.tmplLineForSSHScriptInstance is an ast.Expr, so we need to take .value
                    nodeitem.context_expr.func.value = copy.deepcopy(self.tmplLineOfSshscriptstack.value)
                    ## assign shellbody_visit = <as what>, for example "with $.connect(...) as hello", then
                    ## insert " _sshscript_in_context_ = hello" as the 1st line inside the "with" block.
                    nodeitem.context_expr.func.attr = 'connectAndAppend'
                    #nodeToInsert0 = copy.deepcopy(self.tmplLineBelowWithConnect)
                    if nodeitem.optional_vars is not None:
                        assert nodeitem.optional_vars.id , '"as whatever" is required'
                    else:
                        nodeitem.optional_vars = ast.Name(id=self.genConsoleName(),ctx=ast.Store())
                        pass
                    
                    ## we need this block to solve the issue (connect inside with-connect) like:
                    ## with $.connect():
                    ##     $.connect() <- won't translate correctly if wihtout this iteration
                    ##     $.close()   <- won't translate correctly if wihtout this iteration
                    #if 0:
                    #    ##  disabled, it seems that this is not necessary
                    #    self.insideWith.append(False)
                    #    for item in node.body:
                    #        self.generic_visit(item)
                    #    self.insideWith.pop()
                    
                    #node.body.insert(0, nodeToInsert0)
                    #node.body.append(copy.deepcopy(self.tmplLineAfterWithConnect))
                
                
                elif nodeitem.context_expr.func.attr in ('enter','sudo','su','iterate'):
                    ## convert 
                    ## with $.su as console:
                    ##      ....
                    ## to 
                    ## with $.sudo() as pesudo_console:
                    ##     with pesudo_console.sudo() as console:
                    ##         ...
                    ## (at end)
                    ## console = pesudo_console
                    
                    if len(self.currentConsole):
                        nodeitem.context_expr.func.value.id = self.currentConsole[-1]
                    else:
                        newnode = copy.deepcopy(self.tmplWithSuSudoEnter)
                        ## replace subconsole
                        if nodeitem.optional_vars:
                            subconsole = nodeitem.optional_vars.id
                            topconsole= '_pesudo' + subconsole + '_'
                        else:
                            subconsole = self.genConsoleName()
                            topconsole =  subconsole + '_top'
                        self.currentConsole.append(subconsole)
                        funcname = nodeitem.context_expr.func.attr
                        newnode[1].items[0].optional_vars.id = topconsole
                        newnode[1].body[0].items[0].context_expr.func.value.id = topconsole
                        newnode[1].body[0].items[0].context_expr.func.attr = funcname
                        newnode[1].body[0].items[0].optional_vars.id = subconsole
                        ## replace funcname, args, keywords
                        newnode[1].body[0].items[0].context_expr.args = nodeitem.context_expr.args
                        newnode[1].body[0].items[0].context_expr.keywords = nodeitem.context_expr.keywords
                        newnode[1].body[0].body = node.body
                        ## replace subconsole at the end
                        newnode[1].body[1].value.id = topconsole
                        def callback(node):
                            self.insideSubshell = False
                            self.currentConsole.pop()
                            return node
                        self.insideSubshell = True
                        node._callback_ = callback
        elif isinstance(node, ast.Call) and \
            isinstance(node.func, ast.Attribute) and \
            ( (isinstance(node.func.value, ast.Name) and \
               node.func.value.id == '_sshscript_in_context_') or \
               (isinstance(node.func.value, ast.Subscript) and \
                isinstance(node.func.value.value,ast.Name) and \
                node.func.value.value.id == '_sshscriptstack_') 
            ) and \
            node.func.attr in ('connect','open') and (not self.insideWith[-1]):
            
            self.containsSSHScriptStack[-1] = True
            ## rewrite _sshscript_in_context_.connect() to
            ## _new_sshcript = _sshscriptstack_.connectAndAppend('timwang@rms1', password='tech168')
            nodeToInsert = copy.deepcopy(self.tmplLineForConnect)
            nodeToInsert.value.args = node.args
            nodeToInsert.value.keywords = node.keywords

            ## before changing self.currentExpr, let's verify our idea in advance
            parentContent = ast.unparse(self.currentExpr).strip()
            nodeContent = ast.unparse(node).strip()
            ## if self.currentExpr is a ast.Expr they should the same
            ## if self.currentExpr is a ast.Assign nodeContent should be included in the parentContent
            if not ((parentContent == nodeContent) or parentContent.find(nodeContent) != -1):
                raise ValueError(f'"{parentContent}" not same as "{nodeContent}"')

            if isinstance(self.currentExpr,ast.Assign):
                ## nodeToInsert is a ast.Assign
                ## eg. s = $.connect()
                ## change to s = _new_sshcript = _sshscriptstack_.connectAndAppend()
                pass ## handle later (by assigning _callback)
                
            elif isinstance(self.currentExpr,ast.Return):
                pass ## handle later (by assigning _callback)
            else:
                newnode = nodeToInsert
            
            
            assert self.currentExpr.parent
            box = self.currentExpr.parent
            parentNode = self.currentExpr
            try:
                idx = box.body.index(parentNode)
            except ValueError:
                if isinstance(box, ast.If):
                    ## search "else"
                    idx = box.orelse.index(parentNode)
                    if isinstance(self.currentExpr,ast.Return):
                        """
                        case like:
                        def connect(session=None):
                            if session is not None:
                                return session.connect('user@host1','1234')
                            else:
                                return $.connect('user@host1','1234')
                        """                        
                        def _callback_(node):
                            node.value = ast.Name(id='_new_sshcript')
                            return [nodeToInsert,node]
                        self.currentExpr._callback_ = _callback_
                    else:
                        pass
                else:
                    raise
            else:
                if isinstance(self.currentExpr,ast.Return):
                    ## case like:
                    ## def connect():
                    ##    return $.connect('user@host1','1234')
                    def _callback_(node):
                        node.value = ast.Name(id='_new_sshcript')
                        return [nodeToInsert,node]
                    self.currentExpr._callback_ = _callback_                    
                elif isinstance(self.currentExpr,ast.Assign):
                    ## nodeToInsert is a ast.Assign
                    ## eg. s = $.connect()
                    ## change to s = _new_sshcript = _sshscriptstack_.connectAndAppend()
                    def _callback_(node):
                        node.value = nodeToInsert.value
                        node.targets.extend(nodeToInsert.targets)
                        return node
                    self.currentExpr._callback_ = _callback_ 
                    pass
                else:
                    pass

        elif isinstance(node, ast.Call) and \
            isinstance(node.func, ast.Attribute) and \
            ( (isinstance(node.func.value, ast.Name) and \
               node.func.value.id == '_sshscript_in_context_') or \
               (isinstance(node.func.value, ast.Subscript) and \
                isinstance(node.func.value.value, ast.Name) and \
               node.func.value.value.id == '_sshscriptstack_') 
            ) and \
            node.func.attr == 'close' and \
            (not self.insideWith[-1]):
            
            self.containsSSHScriptStack[-1] = True
            ## rewrite __sshscript_in_context_.close to _sshscriptstack_.closeAndPop()
            newnode = copy.deepcopy(self.tmplLineAfterClose)
            ## verify our idea about "parentNode"
            parentContent = ast.unparse(self.currentExpr)
            nodeContent = ast.unparse(node)
            assert parentContent.strip() == nodeContent.strip(),f'{parentContent} not same as {nodeContent}'
            assert hasattr(self.currentExpr,'parent'), f'{ast.dump(self.currentExpr)} has no .parent'
        elif isinstance(node, ast.Attribute) and \
            isinstance(node.value, ast.Name) and \
            node.value.id in ('_sshscript_in_context_','_c'):
            self.containsSSHScriptStack[-1] = True
            if node.attr in ('connect','open'):
                node.value = copy.deepcopy(self.tmplLineOfSshscriptstack.value)
                node.attr = 'connectAndAppend'
            elif node.attr in ('close','disconnect'):
                node.value = copy.deepcopy(self.tmplLineOfSshscriptstack.value)
                node.attr = 'closeAndPop'
            else:
                if len(self.currentConsole) :
                    node.value.id = self.currentConsole[-1]
                    #elif node.attr in SSHScriptDollar.exportedProperties:
                elif node.attr in __main__.SSHScriptDollarExportedNames:
                    ## eg. _c.stdout, _c.stderr,_c.exitcode keep _c, do not change to _sshscriptstack_[-1]
                    pass
                else:
                    node.value = copy.deepcopy(self.tmplLineForSSHScriptInstance.value)
        elif isinstance(node,ast.Call):
            if isinstance(node.func,ast.Name):
                if len(self.currentConsole):
                    ##         with $.sudo as shell:
                    ## convert:     $hostname 
                    ## to:          shell.sendline(hostname)
                    consolename = self.currentConsole[-1]
                    if node.func.id=='onedollar': 
                        node.func = ast.Attribute(value=ast.Name(id=consolename,ctx=ast.Load()),attr='sendline')
                        del node.args[1:]
                        ## eg. $hostname
                        if isinstance(node.args[0],ast.Constant):
                            node.args[0].value = node.args[0].value.strip()
                        ## eg. $f'{command}'
                        elif isinstance(node.args[0],ast.JoinedStr):
                            for value in node.args[0].values:
                                if isinstance(value,ast.Constant):
                                    ## restore "$." in f-string if it does not in {} for evaluation
                                    ## since this value would put into a f-string again, so we need to escape the escape again
                                    value.value = value.value.replace('DOLLARDOT.','$.').replace('\\','\\\\')
                                elif isinstance(value,ast.FormattedValue):
                                    ## restore and convert "$." in f-string if it is in {} for evaluation
                                    walkAndConvert(value.value)
                        else:
                            raise ValueError(f'unexpected node:{ast.dump(node.args[0])}')
                    elif node.func.id=='twodollars': 
                        node.func = ast.Attribute(value=ast.Name(id=consolename,ctx=ast.Load()),attr='sendline')
                        del node.args[1:]
                        if isinstance(node.args[0],ast.Constant):
                            node.args[0].value = node.args[0].value.strip()
                        ## eg. $f'{command}'
                        elif isinstance(node.args[0],ast.JoinedStr):
                            for value in node.args[0].values:
                                if isinstance(value,ast.Constant):
                                    ## restore "$." in f-string if it does not in {} for evaluation
                                    ## since this value would put into a f-string again, so we need to escape the escape again
                                    value.value = value.value.replace('DOLLARDOT.','$.').replace('\\','\\\\')
                                elif isinstance(value,ast.FormattedValue):
                                    ## restore and convert "$." in f-string if it is in {} for evaluation
                                    walkAndConvert(value.value)
                        else:
                            raise ValueError(f'unexpected node:{ast.dump(node.args[0])}')
                else:
                    inwith = False
                    withshell = False
                    fr = 0
                    tmpl = None
                    if node.func.id=='onedollar': 
                        tmpl = self.tmplCommand
                        pass
                    elif node.func.id=='twodollars': 
                        tmpl = self.tmplCommand
                        withshell = True
                    if tmpl is not None:
                        self.containsSSHScriptStack[-1] = True
                        newnode = copy.deepcopy(tmpl.body[0])
                        ## assign cmd
                        command = node.args[0]
                        raw = node.args[1].value
                        if isinstance( command,ast.JoinedStr):
                            for value in command.values:
                                if isinstance(value,ast.Constant):
                                    ## restore "$." in f-string if it does not in {} for evaluation
                                    ## since this value would put into a f-string again, so we need to escape the escape again
                                    value.value = value.value.replace('DOLLARDOT.','$.').replace('\\','\\\\')
                                elif isinstance(value,ast.FormattedValue):
                                    ## restore and convert "$." in f-string if it is in {} for evaluation
                                    walkAndConvert(value.value)
                            
                            newnode.body[0].value = command
                            fr = 1
                        elif isinstance(command,ast.Constant):
                            if raw == 1:
                                fr = 2 
                                ## can not revert to r'string', maybe not necessary, because the value has already been escaped
                                newnode.body[0].value.value = command.value
                            else:
                                newnode.body[0].value.value = command.value
                        ## rewrite _sshscript_in_context_
                        #trynode.body[1].value.args[0].id = self.sshscriptCurrentId
                        ## assign inwith
                        newnode.body[1].value.keywords[0].value.value = inwith
                        ## assign fr
                        newnode.body[1].value.keywords[1].value.value = fr
                        ## assign withshell
                        newnode.body[2].value.args[0].value = withshell
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == 'DOLLARDOT':
                ## something like: with $.open(...)
                converted = pstd.sub(pstdSub, f'$.{node.func.attr}')
                node.func.value.id, node.func.attr = converted.split('.',1)
            else:
                pass
        elif isinstance(node, ast.withitem):
            self.insideWithitem = True
        elif isinstance(node,ast.Constant) and isinstance(node.value, str):
            node.value = node.value.replace('DOLLARDOT.','$.')
        elif isinstance(node,ast.Name) and node.id == 'DOLLARDOT':
            converted = pstd.sub(pstdSub,f'$.{node.attr}')
            node.id, node.attr = converted.split('.',1)                
        
        ## ----------------------------------------------------------------
        if newnode is None:
            super().generic_visit(node)
        elif isinstance(newnode,list):
            for subnode in newnode:
                super().generic_visit(subnode)
        else:
            super().generic_visit(newnode)
        ## ----------------------------------------------------------------

        if hasattr(node,'_callback_'):
            node = node._callback_(node)
        elif hasattr(newnode,'_callback_'):
            newnode = newnode._callback_(newnode)
        

        if isinstance(node, ast.withitem):
            self.insideWithitem = False
        elif isinstance(node, ast.Assign) and hasattr(node,'isDollarAssign'):
            ## convert stdout, stderr, exitcode = $hostname
            ## convert stdout, stderr, exitcode = $$hostname
            self.currentExpr = None
            self.insideDollarAssign = False
            originNode = copy.deepcopy(node)
            delattr(originNode,'isDollarAssign')
            if len(self.currentConsole):
                ## eg. with $ as console:
                ##     stdout,_,_ = $whoami <- this
                ## just do nothing is ok
                pass
            else:
                ## upgrade "try" block one level
                newnode = originNode.value  
                ## this is stdout,stderr,exitcode = $hostname
                originNode.value = copy.deepcopy(self.tmplLineAssignAtBottom).value
                ## disabled, this is stdout = $hostname
                #originNode.value = copy.deepcopy(self.tmplLineAssignStdoutAtBottom).value
                ## append original assignment to last statement
                newnode.finalbody.append(originNode)

        ## decrease scopeDepth
        elif node.__class__ in (ast.FunctionDef,ast.AsyncFunctionDef):

            containsSSHScript = self.containsSSHScriptStack[-1]
            ## keep the initial value of self.containsSSHScriptStack
            if len(self.containsSSHScriptStack) > 1: self.containsSSHScriptStack.pop()

            ## add initial value into self.containsSSHScriptStack for this scope

            name = self.localSSHScriptListKeyStack.pop()
            assert name == node.name            
            
            if containsSSHScript:            
                nodeToInsert = copy.deepcopy(self.tmplLinesBlowDef)
                #nodeToInsert.value.args[0].id = node.name
                ## get sshscript from up scope
                #nodeToInsert.body[1].body[0].value.value.slice.value = self.localSSHScriptListKeyStack[-1]
                #nodeToInsert.body[2].value.value = node.name
                ## append to scope beginning
                node.body.insert(0,nodeToInsert)
                
                #nodeToInsertAtEnd = copy.deepcopy(self.tmplLineAfterDef)
                #node.body.append(nodeToInsertAtEnd)
        elif isinstance(node,ast.Expr):
            self.currentExpr = None
        elif isinstance(node,ast.Assign):
            self.currentExpr = None
        elif isinstance(node,ast.Return):
            self.currentExpr = None
        elif isinstance(node, ast.With):
            self.insideWith[-1] = False
            
            nodeitem = node.items[0]
            if isinstance(nodeitem.context_expr, ast.Call) and \
                isinstance(nodeitem.context_expr.func,ast.Attribute) and \
                ( (isinstance(nodeitem.context_expr.func.value, ast.Name) and \
                nodeitem.context_expr.func.value.id == '_sshscript_in_context_') or \
                (isinstance(nodeitem.context_expr.func.value, ast.Subscript) and \
                    isinstance(nodeitem.context_expr.func.value.value,ast.Name) and \
                nodeitem.context_expr.func.value.value.id == '_sshscriptstack_') 
                ):
                if nodeitem.context_expr.func.attr in ('enter','sudo','su','iterate'):
                    #_ = self.currentConsole.pop()
                    pass
        return newnode or node

def convert(spyscript):
    ## preserve strings in script
    stringTransformer = StringTransformer()
    stringMaskedSpyscript = stringTransformer.mask(spyscript)
    #dumpToLines(stringMaskedSpyscript,'after string-masked')
    maskCommentTransformer = MaskConmmentTransformer(stringTransformer)
    commentMaskedSpyscript = maskCommentTransformer.mask(stringMaskedSpyscript)
    #dumpToLines(commentMaskedSpyscript,'after comment-masked')
    #return ''
    def encapsulate(value):
        if stringTransformer.tokenOnlyPattern.match(value.strip()):
            value = value.strip()
            tokenvalue = stringTransformer.getToken(value)
            ## convert $. to it's python-equivalent
            if value.startswith('f_@@_'):
                stringTransformer.setToken(value, curlybracketInLongString.sub( curlybracketInLongStringSub, tokenvalue))
            else:
                stringTransformer.setToken(value, curlybracketInDollarCommand.sub( curlybracketInDollarCommandSub, tokenvalue))
            ## no need to add triple-quotes 
            return None
        elif stringTransformer.tokenPattern.search(value):
            ## the value contains strings, so let's add it into 3-quotes
            ## eg. $echo @{""" string """}
            for token in stringTransformer.tokenPattern.findall(value):
            #for token in []:
                tokenvalue = stringTransformer.getToken(token)
                ## convert $. to it's python-equivalent
                if token.startswith('f_@@_'):
                    tokenvalue = curlybracketInLongString.sub( curlybracketInLongStringSub, tokenvalue)
                elif token.startswith('r_@@_'):
                    pass
                else:
                    tokenvalue = curlybracketInDollarCommand.sub( curlybracketInDollarCommandSub, tokenvalue)
                ## and escape 3-quotes string inside the string (double quotes only,since it is added into 3-double-quotes)
                #if tokenvalue.startswith('"""') and tokenvalue.endswith('"""'):
                stringTransformer.setToken(token, tokenvalue.replace('"','\\"'))
            value = curlybracketInDollarCommand.sub( curlybracketInDollarCommandSub, value)
            #value = curlybracketInDollarCommandSubNested(stringTransformer, value)
            return value
        else:
            ## convert $. to it's python-equivalent
            value = curlybracketInDollarCommand.sub(curlybracketInDollarCommandSub, value)
            return value          
    ## matching "with $ls", "with $.", "with $$",...
    withPatternAs = re.compile('(\n?[\s\t]*?)with([\s\t]+?)\$([^\n]*?)([\s\t]+)as([\s\t]+.+?[\s\t]?):',re.S)
    withPattern = re.compile('(\n?[\s\t]*?)with([\s\t]+?)\$([^\n]*?)([\s\t]*?):',re.S)
    def subWithPattern(m):
        try:
            ## match withPatternAs
            space0, space1,command,space2,afteras = m.groups()
        except ValueError:
            ## match withPattern
            space0, space1,command,space2 = m.groups()
            afteras = None
        if command.startswith('.'):
            ## eg. with $.connect()
            funcname = ''
            funcnameEnd = ''
            for token in stringTransformer.tokenPattern.findall(command):
                tokenvalue = stringTransformer.getToken(token)
                ## convert $. to it's python-equivalent
                if token.startswith('f_@@_'):
                    tokenvalue = curlybracketInLongString.sub( curlybracketInLongStringSub, tokenvalue)
                elif token.startswith('r_@@_'):
                    pass
                else:
                    tokenvalue = curlybracketInDollarCommand.sub( curlybracketInDollarCommandSub, tokenvalue)
                stringTransformer.setToken(token, tokenvalue)                
            value = pstd.sub(pstdSub, '$' + command)
        else:
            if command.startswith('$'):
                ## twodollars command
                value = command[1:]
            else:
                value = command
            funcname = 'withdollar('
            funcnameEnd = ')'
            raw = 2 if value.startswith('r_@@_') else (1 if value.startswith('f_@@_') else 0)
            encapsulatedValue = encapsulate(value)
            if encapsulatedValue:
                encapsulatedValue = stringTransformer.genToken('""" %s """' % encapsulatedValue.replace('"','\\"'))
            else:
                encapsulatedValue = value
            ## withdollar should has "raw"(fr=2) argument
            value = "%s,%s" % (encapsulatedValue or '""',raw)
        if afteras is None:
            return f'{space0}with{space1}{funcname}{value}{funcnameEnd}:'
        else:
            return f'{space0}with{space1}{funcname}{value}{funcnameEnd}{space2}as{afteras}:'
    dollarMaskedSpyscript = withPatternAs.sub(subWithPattern,commentMaskedSpyscript)
    dumpToLines(dollarMaskedSpyscript,'after with-transformed-as')
    dollarMaskedSpyscript = withPattern.sub(subWithPattern,dollarMaskedSpyscript)
    dumpToLines(dollarMaskedSpyscript,'after with-transformed-no-as')
    ## exclude "with $..."
    dollarPattern = re.compile('(?<!with)([ \t]*?)\$(.*)',re.M)
    def subDollarPattern(m):
        space0, command = m.groups()
        if command.startswith('.'):
            for token in stringTransformer.tokenPattern.findall(command):
                tokenvalue = stringTransformer.getToken(token)
                ## convert $. to it's python-equivalent
                if token.startswith('f_@@_'):
                    tokenvalue = curlybracketInLongString.sub( curlybracketInLongStringSub, tokenvalue)
                elif token.startswith('r_@@_'):
                    pass
                else:
                    tokenvalue = curlybracketInDollarCommand.sub( curlybracketInDollarCommandSub, tokenvalue)
                stringTransformer.setToken(token, tokenvalue)                
            return space0 +  pstd.sub(pstdSub, '$' + command)
        else:
            if command.startswith('$'):
                ## twodollars command
                value = command[1:]
                funcname = 'twodollars('
            else:
                value = command
                funcname = 'onedollar('
            funcnameEnd = ')'
            raw = 1 if value.startswith('r_@@_') else 0

            encapsulatedValue = encapsulate(value)

            if encapsulatedValue:
                encapsulatedValue = stringTransformer.genToken('""" %s """' % encapsulatedValue.replace('"','\\"'))
            else:
                encapsulatedValue = value
            value = f"{encapsulatedValue},{raw}"
        return f'{space0}{funcname}{value}{funcnameEnd}'
    transformedSpyscript = dollarPattern.sub(subDollarPattern,dollarMaskedSpyscript)
    dumpToLines(transformedSpyscript,'after dollar-transformed')

    transformedSpyscript = stringTransformer.restore(transformedSpyscript)
    dumpToLines(transformedSpyscript,'after string restored')
    #return ''

    ## replace $.<var>
    ## Let statements like "a = $.stdout" to be replaced and be able to be parsed by ast.parse
    #transformedSpyscript = pstd.sub(pstdSub, transformedSpyscript)

    #dumpToLines(transformedSpyscript,'after-string-restored')
    ## strip leading spaces is necessary before ast.parse
    transformedSpyscript = stripLeadingSpace(transformedSpyscript)
    dumpToLines(transformedSpyscript,'lark-complete')
    #return ''
    
    try:
        tree = ast.parse(transformedSpyscript)
    except SyntaxError:
        dumpToLines(transformedSpyscript,'ast-err-')
        raise
    else:
        
        ## converting to regular python script
        pyTree = DollarChanger().visit(tree)
        ## seems useless
        #pyTree = ast.fix_missing_locations(pyTree)
        pyScript = ast.unparse(pyTree)       
        return pyScript
