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

## 2025/3/2
## convert .spy token parsed results to valid python script
import ast
import copy
import __main__

class DollarChanger(ast.NodeTransformer):
    """
    A NodeTransformer that converts SSH script syntax with dollar signs ($) to valid Python code.
    
    This class transforms AST nodes that contain SSH script syntax (like $.connect, $hostname)
    into valid Python code that can be executed. It handles various SSH script constructs
    including connections, shell commands, and context managers.
    """
    tmplLinesAtBeginning = ast.parse('_sshscriptstack_ = threading.current_thread().sshscriptstack').body[0]
    ## with-exit would close the session, so, this is pop() not popAndClose()
    tmplLineForConnect = ast.parse('_new_sshcript = _sshscriptstack_.connect("", password="")').body[0]
    tmplLineOfSshscriptstack = ast.parse('_sshscriptstack_').body[0]
    tmplLineForSSHScriptInstance = ast.parse('_sshscriptstack_[-1]').body[0]
    tmplLineForSSHScriptInstanceShell = ast.parse('_sshscriptstack_[-1].shell(arg)').body[0]
    tmplLineAfterClose = ast.parse('_sshscriptstack_.close()').body[0]
    tmplLineForNewScope = ast.parse('_sshscriptstack_ = threading.current_thread().sshscriptstack').body[0]
    #tmplLinesBlowDef = ast.parse("_sshscriptstack_ = sys._getframe(1).f_locals.get('_sshscriptstack_') or threading.current_thread().sshscriptstack").body[0]
    #tmplLinesBlowDef = ast.parse("_sshscriptstack_ = threading.current_thread().sshscriptstack or sys._getframe(1).f_locals.get('_sshscriptstack_')").body[0]
    tmplLinesBlowDef = ast.parse("_sshscriptstack_ = threading.current_thread().sshscriptstack").body[0]
    tmplLineAssignAtBottom = ast.parse('a=_c.stdout, _c.stderr').body[0]
    
    def __init__(self):
        """
        Initialize the DollarChanger transformer.
        
        Sets up internal state variables to track the transformation process,
        including stacks for tracking scope, console names, and various flags.
        """
        super().__init__()
        self.insideWith = [False]
        self.insideWithitem = False
        self.insideDollarAssign = False
        self.insideSubshell = False
        self.currentExpr = None
        self.localSSHScriptListKeyStack = ['0']
        ##  initial value is for Module, suppose it is False
        self.containsSSHScriptStack = [False]
        self.currentConsole = []
        self.consoleSerialNo = 0
        
    def _gen_console_name(self):
        """
        Generate a unique console name for SSH script contexts.
        
        Returns:
            str: A unique console name in the format '_pesudoN' where N is an incrementing number.
        """
        self.consoleSerialNo += 1
        return f'_pesudo{self.consoleSerialNo}'
        
    def generic_visit(self, node):
        """
        Visit a node in the AST and transform it if necessary.
        
        This is the main transformation method that handles various AST node types
        and converts SSH script syntax to valid Python code.
        
        Args:
            node: The AST node to visit and potentially transform.
            
        Returns:
            The transformed node or the original node if no transformation was needed.
        """
        newnode = None
        if hasattr(node,'body') and isinstance(node.body,list):
            ## ast.IfExp (eg. if '$HOME\n' == _c.stdout else 0) has .body, but it is a ast.Constant
            ## so we add the condition "isinstance(node.body,list)"
            try:
                for child in node.body:
                    child.parent = node
                if isinstance(node,ast.If):
                    for child in node.orelse:
                        child.parent = node
            except:
                print('Error %s' % ast.unparse(node))
                print('Error node:',ast.dump(node))
                raise
        def walkAndConvert(v):            
            if isinstance(v, ast.BinOp):
                walkAndConvert(v.left)
                walkAndConvert(v.right)
            elif isinstance(v, ast.Call):
                for arg in v.args:
                    walkAndConvert(arg)
                for k in v.keywords:
                    walkAndConvert(k.value)   

        if isinstance(node,ast.Expr):
            self.currentExpr = node
        elif isinstance(node,ast.Assign):
            self.currentExpr = node
        elif isinstance(node,ast.Return):
            self.currentExpr = node
        

        ## increase scopeDepth
        if node.__class__ in (ast.FunctionDef,ast.AsyncFunctionDef):
            self.localSSHScriptListKeyStack.append(node.name)
            ## add initial value into self.containsSSHScriptStack for this scope
            self.containsSSHScriptStack.append(False)
        elif isinstance(node, ast.With):
            self.insideWith[-1] = True
        elif isinstance(node, ast.Assign) and isinstance(node.value,ast.Call) and\
                isinstance(node.value.func,ast.Name) and node.value.func.id in ('exec_command','onedollar','twodollars'):
            ## convert stdout, stderr, exitcode = $hostname
            ## convert stdout, stderr, exitcode = $$hostname
            self.insideDollarAssign = True
            node.isDollarAssign = True
        
        ## ------------------ node modification starts ------------------
        if isinstance(node, ast.Module):
            def module_callback(node):
                if self.tmplLinesAtBeginning:
                    node.body.insert(0,copy.deepcopy(self.tmplLinesAtBeginning))
                return node
            node._callback_ = module_callback
        elif isinstance(node, ast.With): 
            nodeitem = node.items[0]
            #print('========',ast.dump(nodeitem,indent=4))
            if isinstance(nodeitem.context_expr, ast.Attribute) and \
                isinstance(nodeitem.context_expr.value,ast.Name) and \
                nodeitem.context_expr.value.id=='_sshscript_in_context_' and\
                nodeitem.context_expr.attr=='session':
                ## eg. with _sshscript_in_context_.session as console1:
                ## optional_vars is the variable name after "as"
                if nodeitem.optional_vars is None:
                    nodeitem.optional_vars = ast.Name(id=self._gen_console_name(),ctx=ast.Load())
                self.currentConsole.append(nodeitem.optional_vars.id)
                def callback(node):
                    self.currentConsole.pop()
                    return node
                node._callback_ = callback

            elif isinstance(nodeitem.context_expr, ast.Call) and \
                isinstance(nodeitem.context_expr.func,ast.Name) and \
                nodeitem.context_expr.func.id=='withdollar':
                
                self.containsSSHScriptStack[-1] = True                
                ## eg:
                ## with $.sudo 
                ##     with $#!/bin/bash
                
                if len(self.currentConsole):
                    ## conver to console.shell()
                    nodeitem.context_expr.func.id = 'shell'
                    nodeitem.context_expr.func = ast.Attribute(value=ast.Name(id=self.currentConsole[-1],ctx=ast.Load()),attr='shell')
                    ## only keep the 1st argument, which is the shell
                    del nodeitem.context_expr.args[1:]
                    ## optional_vars is the variable name after "as"
                    if nodeitem.optional_vars is None:
                        nodeitem.optional_vars = ast.Name(id=self._gen_console_name(),ctx=ast.Load())
                    self.currentConsole.append(nodeitem.optional_vars.id)
                    def callback(node):
                        self.currentConsole.pop()
                        return node
                    node._callback_ = callback
                else:
                    ## conver to _sshscriptstack_[-1].shell()
                    args = nodeitem.context_expr.args
                    keywords = nodeitem.context_expr.keywords
                    nodeitem.context_expr = copy.deepcopy(self.tmplLineForSSHScriptInstanceShell.value)
                    nodeitem.context_expr.args = args
                    nodeitem.context_expr.keywords = keywords

                    ## optional_vars is the variable name after "as"
                    if nodeitem.optional_vars is None:
                        nodeitem.optional_vars = ast.Name(id=self._gen_console_name(),ctx=ast.Load())
                    self.currentConsole.append(nodeitem.optional_vars.id)
                    def callback(node):
                        self.currentConsole.pop()
                        return node
                    node._callback_ = callback
            ## with $.session.open(), $.session.enter(),...
            elif isinstance(nodeitem.context_expr, ast.Call) and \
                isinstance(nodeitem.context_expr.func,ast.Attribute) and \
                isinstance(nodeitem.context_expr.func.value, ast.Attribute) and\
                nodeitem.context_expr.func.value.value.id == '_sshscript_in_context_' and\
                nodeitem.context_expr.func.value.attr == 'session':
                
                if len(self.currentConsole):
                    ## replace _sshscript_in_context_ with console's name
                    nodeitem.context_expr.func.value.id = self.currentConsole[-1]

                    if nodeitem.optional_vars is None:
                        nodeitem.optional_vars = ast.Name(id=self._gen_console_name(),ctx=ast.Store())                    
                    self.currentConsole.append(nodeitem.optional_vars.id)
                    def callback(node):
                        self.currentConsole.pop()
                        return node
                    node._callback_ = callback
                else:
                    nodeitem.context_expr.func.value.value = copy.deepcopy(self.tmplLineForSSHScriptInstance.value)
                    if nodeitem.optional_vars is None:
                        nodeitem.optional_vars = ast.Name(id=self._gen_console_name(),ctx=ast.Load())
                    self.currentConsole.append(nodeitem.optional_vars.id)
                    def callback(node):
                        self.currentConsole.pop()
                        return node
                    node._callback_ = callback                
            ## with $.connect, $.open
            ## with $.shell, $.enter, $.sudo, $.su, $.iterate
            elif isinstance(nodeitem.context_expr, ast.Call) and \
                isinstance(nodeitem.context_expr.func,ast.Attribute) and \
                ( 
                    (isinstance(nodeitem.context_expr.func.value, ast.Name)      and nodeitem.context_expr.func.value.id == '_sshscript_in_context_') \
                    or \
                    (isinstance(nodeitem.context_expr.func.value, ast.Subscript) and  isinstance(nodeitem.context_expr.func.value.value,ast.Name) and nodeitem.context_expr.func.value.value.id == '_sshscriptstack_')
                ):
                if nodeitem.context_expr.func.attr in ('connect','open'):
                    ## self.tmplLineForSSHScriptInstance is an ast.Expr, so we need to take .value
                    if len(self.currentConsole):
                        nodeitem.context_expr.func.value.id = self.currentConsole[-1]
                        ## keep value of nodeitem.context_expr.func.attr 
                    else:
                        nodeitem.context_expr.func.value = copy.deepcopy(self.tmplLineOfSshscriptstack.value)
                        #nodeitem.context_expr.func.attr = 'connectAndAppend'
                        nodeitem.context_expr.func.attr = 'connect'
                    ## assign shellbody_visit = <as what>, for example "with $.connect(...) as hello", then
                    ## insert " _sshscript_in_context_ = hello" as the 1st line inside the "with" block.
                    if nodeitem.optional_vars is None:
                        nodeitem.optional_vars = ast.Name(id=self._gen_console_name(),ctx=ast.Store())                    
                    self.currentConsole.append(nodeitem.optional_vars.id)
                    def callback(node):
                        self.currentConsole.pop()
                        return node
                    node._callback_ = callback

                elif nodeitem.context_expr.func.attr in ('new_session','shell','enter','sudo','su','iterate'):
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
                        
                        ## replace _sshscript_in_context_ with console's name
                        nodeitem.context_expr.func.value.id = self.currentConsole[-1]

                        if nodeitem.optional_vars is None:
                            nodeitem.optional_vars = ast.Name(id=self._gen_console_name(),ctx=ast.Store())                    
                        self.currentConsole.append(nodeitem.optional_vars.id)
                        def callback(node):
                            self.currentConsole.pop()
                            return node
                        node._callback_ = callback
                    else:
                        ## conver top level $.enter() to _sshscriptstack_[-1].enter()
                        args = nodeitem.context_expr.args
                        keywords = nodeitem.context_expr.keywords
                        funcname = nodeitem.context_expr.func.attr
                        nodeitem.context_expr = copy.deepcopy(self.tmplLineForSSHScriptInstanceShell.value)
                        nodeitem.context_expr.args = args
                        nodeitem.context_expr.keywords = keywords
                        nodeitem.context_expr.func.attr = funcname
                        ## optional_vars is the variable name after "as"
                        if nodeitem.optional_vars is None:
                            nodeitem.optional_vars = ast.Name(id=self._gen_console_name(),ctx=ast.Load())
                        self.currentConsole.append(nodeitem.optional_vars.id)
                        def callback(node):
                            self.currentConsole.pop()
                            return node
                        node._callback_ = callback
                else:
                    raise ValueError(f'with $.{nodeitem.context_expr.func.attr} is not supported')
        elif isinstance(node, ast.Call) and \
            isinstance(node.func, ast.Attribute) and \
            ( (isinstance(node.func.value, ast.Name) and \
               node.func.value.id == '_sshscript_in_context_') or \
               (isinstance(node.func.value, ast.Subscript) and \
                isinstance(node.func.value.value,ast.Name) and \
                node.func.value.value.id == '_sshscriptstack_') 
            ) and \
            node.func.attr in ('connect','open') and (not self.insideWith[-1]):           
            
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
            
            #self.containsSSHScriptStack[-1] = True
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
            if node.attr in ('connect','open'):
                node.value = copy.deepcopy(self.tmplLineOfSshscriptstack.value)
                node.attr = 'connect' ## normalize to "connect"
            elif node.attr in ('close','disconnect'):
                node.value = copy.deepcopy(self.tmplLineOfSshscriptstack.value)
                node.attr = 'close' ## normalize to "close"
            else:
                if len(self.currentConsole) > 0 :
                    if self.insideWithitem:
                        ## in case of "with $.connect(f'user@{$.stdout.strip()}',password='1234') as host2:"
                        ## we need to convert $.stdout to _sshscriptstack_[-1].stdout, not host2.stdout
                        if len(self.currentConsole) > 1:
                            node.value.id = self.currentConsole[-2]
                        else:
                            node.value = copy.deepcopy(self.tmplLineForSSHScriptInstance.value)
                    else:
                        node.value.id = self.currentConsole[-1]
                ## v2.0.3 , 因為不再產生 _c ，所以_c.stdout, _c.stderr,_c.exitcode 都要改成 _sshscriptstack_[-1].xxx
                #elif 0 and node.attr in __main__.DollarExportedNames:
                #    pass
                else:
                    ## eg. _c.stdout, _c.stderr,_c.exitcode keep _c, change to _sshscriptstack_[-1]
                    node.value = copy.deepcopy(self.tmplLineForSSHScriptInstance.value)
        
        ## treatment for $.include (even it is inside with)
        ## if the arguments of include() is not a string, replace "include" with "runtimeInclude"
        elif isinstance(node, ast.Call) and \
            isinstance(node.func, ast.Attribute) and \
            isinstance(node.func.value, ast.Name) and \
            node.func.value.id == '_sshscript_in_context_' and \
            node.func.attr == 'include':
            if not (len(node.args)==1 and isinstance(node.args[0],ast.Constant)):
                node.func.attr = 'runtimeInclude'
        
        elif isinstance(node,ast.Call):   
            if isinstance(node.func,ast.Name):
                if len(self.currentConsole):
                    ##         with $.sudo as shell:
                    ## convert:     $hostname 
                    ## to:          shell.send_line(hostname)
                    consolename = self.currentConsole[-1]
                    if node.func.id in ('exec_command','onedollar','twodollars'):
                        node.func = ast.Attribute(value=ast.Name(id=consolename,ctx=ast.Load()),attr='send_line')
                        
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
                                    ## 2024/1/27 cancel escape of \ , aka #.replace('\\','\\\\')

                                    ## v2.0.3 DOLLARDOT 可能已經是上古遺跡，暫時取消
                                    #value.value = value.value.replace('DOLLARDOT.','$.')
                                    pass
                                elif isinstance(value,ast.FormattedValue):
                                    ## restore and convert "$." in f-string if it is in {} for evaluation
                                    walkAndConvert(value.value)
                        else:
                            ## eg. $(chr(3)+'\n')
                            pass
                        node.keywords = [
                            keyword for keyword in node.keywords
                            if keyword.arg not in ('shell','shell_executable','_legacy_twodollars')
                        ]
                elif node.func.id in ('exec_command','onedollar','twodollars'):
                    newnode = copy.deepcopy(self.tmplLineForSSHScriptInstanceShell.value)
                    newnode.func.attr = 'exec_command'
                    ## Preserve command arguments and execution overrides.
                    newnode.args = node.args[:]
                    newnode.keywords = node.keywords[:]
        elif isinstance(node, ast.withitem):
            self.insideWithitem = True
        elif isinstance(node,ast.Name) and node.id in ('_sshscript_in_context_', '_sshscriptstack_'):
            self.containsSSHScriptStack[-1] = True
        
        ## ----------------------------------------------------------------
        if newnode is None:
            super().generic_visit(node)
        elif isinstance(newnode,list):
            for subnode in newnode:
                super().generic_visit(subnode)
        else:
            super().generic_visit(newnode)
        
        ## ---------------------------
        ## Bottom-up visiting starts
        ## ---------------------------

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
                if isinstance(originNode.value,ast.Try):
                    newnode = originNode.value  
                    ## eg. stdout,stderr = $hostname
                    originNode.value = copy.deepcopy(self.tmplLineAssignAtBottom).value
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
                ## append to scope beginning
                node.body.insert(0,nodeToInsert)
                
        elif isinstance(node,ast.Expr):
            self.currentExpr = None
        elif isinstance(node,ast.Assign):
            self.currentExpr = None
        elif isinstance(node,ast.Return):
            self.currentExpr = None
        elif isinstance(node, ast.With):
            self.insideWith[-1] = False
            
        return newnode or node
