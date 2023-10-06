# Define a new Thread class that has a parent attribute
import threading
import time
import sys,os


class SshscriptStack(object):
    instances = []
    @classmethod
    def maintain(cls):
        dead = []
        for inst in cls.instances:
            if inst.owner.is_alive(): continue
            dead.append(inst)
        for inst in dead:
            cls.instances.remove(inst)
    @classmethod
    def popFromAllInstances(cls,session):
        for inst in cls.instances:
            if session in inst.stack:
                inst.stack.remove(session)
            for _,stack in inst.savedStack.items():
                if session in stack:
                    stack.remove(session)
        SshscriptStack.maintain()
    def __init__(self,owner,initialstack=None):
        self.stack = initialstack or []
        assert isinstance(self.stack,list)
        self.savedStack = {}
        self.owner = owner
        SshscriptStack.instances.append(self)
    def __len__(self):
        return len(self.stack) 
    def pushLayer(self,initialItems):
        retoreId = time.time()
        self.savedStack[retoreId] = self.stack
        self.stack = SshscriptStack(self.owner,initialItems)
        return retoreId
    def popLayer(self,savedId):
        self.stack = self.savedStack[savedId]
        del self.savedStack[savedId]    
    def append(self,x):
        self.stack.append(x)
    def pop(self,*args):
        session = self.stack.pop(*args)
        SshscriptStack.popFromAllInstances(session)
        return session
    def __iter__(self):
        return iter(self.stack) 
    def __getitem__(self, val): 
        return self.stack[val]
    ## functions to let parser adds one line only 
    def connectAndAppend(self,*args, **kwargs):
        session = self[-1].connect(*args, **kwargs)
        self.append(session)
        session.ownerstack = self
        return session
    def closeAndPop(self):
        self[-1].close()
        self.pop()



def monkeyPatchThread__init__():
    originalThread_init = threading.Thread.__init__
    def newThread_init(self, *args, **kwargs):
        self.parent = threading.current_thread()
        self.ctime = time.time()
        try:
            self.sshscriptstack = SshscriptStack(self,[kwargs['_sshscript_session_']])
        except KeyError:
            ## called by threading.Thread
            try:
                self.sshscriptstack = SshscriptStack(self, [self.parent.sshscriptstack[-1]])
            except AttributeError:
                ## parent thread is main thread
                self.sshscriptstack = SshscriptStack(self)
            except IndexError:
                ## maybe other lib (like paramiko) calls for new thread
                self.sshscriptstack = SshscriptStack(self)
        else:
            ## called by $.thread()
            del kwargs['_sshscript_session_']
        originalThread_init(self,*args, **kwargs)
    threading.Thread.__init__ = newThread_init
    
    ## debuging
    if os.environ.get('DEBUG'):
        with open(os.path.join(os.path.dirname(__file__),'__init__.py')) as fd:
            for line in fd:
                p = line.find('__version__')
                if p != -1:
                    sys.stderr.write(f'monkey patch Thread.__init__ completed, {line[p:]}')
                    break
monkeyPatchThread__init__()
