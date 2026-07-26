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
# Define a new Thread class that has a parent attribute
import threading
import time
import sys
from collections import deque
class SshscriptStack(object):
    """
    A stack-like data structure that maintains a thread-safe collection of SSH session objects.
    
    This class implements a stack with a maximum length limit and provides methods
    for managing SSH sessions within a thread context. It maintains a history of
    sessions and allows for session management operations.
    
    Attributes:
        instances (list): Class-level list tracking all instances of SshscriptStack
        stack (deque): The main storage container for session objects
        owner (threading.Thread): The thread that owns this stack instance
    """
    #instances = []
    def __init__(self,owner,initialitems=None):
        """
        Initialize a new SshscriptStack instance.
        
        Args:
            owner (threading.Thread): The thread that owns this stack instance
            initialitems (list, optional): Initial items to populate the stack with
        """
        self.stack = deque(initialitems,maxlen=300) if initialitems else deque(maxlen=300)
        assert isinstance(self.stack,deque),type(self.stack)
        ## the thread which owns this stack
        self.owner = owner
        self.locker = threading.Lock()
        #SshscriptStack.instances.append(self)
    
    def __len__(self):
        """
        Get the current size of the stack.
        
        Returns:
            int: The number of items in the stack
        """
        return len(self.stack) 

    def __iter__(self):
        """
        Create an iterator for the stack.
        
        Returns:
            iterator: An iterator over the stack's contents
        """
        return iter(self.stack) 

    def __getitem__(self, val): 
        """
        Get an item from the stack by index.
        
        Args:
            val: The index or slice to retrieve
            
        Returns:
            The item at the specified index or slice
        """
        if val > 0:
            assert len(self.stack) < val , f'len of stack:{len(self.stack)}, No item for "{val}"'
        elif val == 0:
            assert len(self.stack) > 0 , f'len of stack:{len(self.stack)}, No item for "{val}"'
        else:
            assert len(self.stack) >= abs(val) , f'len of stack:{len(self.stack)}, No item for "{val}"'

        return self.stack[val]

    def getLastIndex(self,item):
        """
        Find the index of the last occurrence of an item in the stack.
        
        Args:
            item: The item to search for
            
        Returns:
            int: The index of the last occurrence, or -1 if not found
        """
        start = 0
        idx = -1
        while True:
            try:
                idx = self.stack.index(item,start)
            except ValueError:
                break
            else:
                start = idx + 1
        return idx

    def append(self,x):
        """
        Add an item to the top of the stack.
        
        Args:
            x: The item to append to the stack
        """
        try:
            self.locker.acquire()
            self.stack.append(x)
        finally:
            self.locker.release()
            pass
    def pop(self,x=None):
        """
        Remove and return an item from the stack.
        
        Args:
            x (optional): The specific item to remove. If None, removes the top item.
            
        Returns:
            The removed item
            
        Raises:
            AssertionError: If the specified item is not at the top of the stack
        """
        self.locker.acquire()
        try:
            if isinstance(self.stack,SshscriptStack):
                assert self.stack[-1] == x
                session = self.stack.remove(x)
            elif x is None:
                session = self.stack.pop()
            else:
                assert isinstance(self.stack,deque),f'{id(self.owner)}:{self.stack} is not deque({isinstance(self.stack,SshscriptStack)})'
                ## find the index of last item of n (rindex)
                idx = self.getLastIndex(x)
                if 1:
                    if not idx == len(self.stack) - 1:
                        exc_info = sys.exc_info()
                        if exc_info[0] is not None:
                            raise exc_info[1]
                        else:
                            raise RuntimeError(f"{id(self.owner)}:{x} is not on top of ({self.stack})")
                    self.stack.pop()
                else:
                    for i in range(idx,len(self.stack)):
                        x = self.stack.pop()
                ## instance of Session or wcw (channel wrapper)
                session = x        
            return session
        finally:
            self.locker.release()    
    ## v2.0.3, divert to session's __enter__() 
    def connect(self,*args, **kwargs):
        """
        Connect using the session at the top of the stack.
        
        Args:
            *args: Positional arguments for the connection
            **kwargs: Keyword arguments for the connection
            
        Returns:
            The connected session
        """
        return self[-1].connect(*args, **kwargs)

    def close(self):
        """
        Close the session at the top of the stack.
        
        Returns:
            The result of closing the session
        """
        return self[-1].close()
    def __del__(self):
        #SshscriptStack.instances.remove(self)
        pass

'''
2026/5/27: is maintening_job still required?
maintening_threads = set()
def maintening_job():
    while True:
        dropable_sessions = set()
        for t in list(maintening_threads):
            if t.is_alive(): continue
            for s in t.sshscriptstack.stack:
                if not s.connected:
                    dropable_sessions.add((t,s))
            maintening_threads.remove(t)
            #print('live session in dead thread',t,'total=',len(dropable_sessions))
        for t,s in dropable_sessions:
            print('removing',s,'from',t)
            try:
                s.unbindThread(t)
            except IndexError:
                pass
        time.sleep(3)
'''

def _monkey_patch_thread_init_():
    """
    Monkey patch the threading.Thread.__init__ method to add SSH script functionality.
    
    This function modifies the Thread class initialization to:
    1. Add a parent thread reference
    2. Add a creation time timestamp
    3. Initialize an SSH script stack for the thread
    
    The patching enables SSH session management within threads and maintains
    proper session context across thread creation.
    """
    originalThread_init = threading.Thread.__init__
    def patched_init(self, *args, **kwargs):
        """
        Patched initialization method for Thread class.
        ( .parent, .ctime and .sshscriptstack are added to an instance of Thread)
        
        Args:
            *args: Original positional arguments
            **kwargs: Original keyword arguments, may include _sshscript_session_
        """
        self.parent = threading.current_thread()
        self.ctime = time.time()
        
        
        if 'no_patch' in kwargs:
            ## these are sshscript's thread
            no_patch = kwargs['no_patch']
            del kwargs['no_patch']
        elif (self.__class__.__name__ in ('Transport','Timer')):
            ## these are paramiko's thread
            no_patch = True
        else:
            no_patch = False
        
        if not no_patch:
            try:
                ## called by ssshscripsession.thread()
                self.sshscriptstack = SshscriptStack(self,[kwargs['_sshscript_session_']])
                del kwargs['_sshscript_session_']
            except KeyError:
                ## called by threading.Thread
                self.sshscriptstack = SshscriptStack(self)
                ## pro: 
                ## cons: not threads-safe, requires "with $.new_session()" 
                ##   (2026/5/27: need more explaination, why not threads-safe? why need "with $.new_session()"?)
                if len(self.parent.sshscriptstack):
                    self.sshscriptstack.append(self.parent.sshscriptstack[-1])
                
        originalThread_init(self,*args, **kwargs)
    threading.Thread.__init__ = patched_init   

_monkey_patch_thread_init_()
## v2.0.3 added
## As for main_thread, it would enable a .py file can import *.spy by
## adding one line "import sshscriptsession" only.
## see unitest-v2.0.3/B03nametest.py for example
for t in threading.enumerate():
    if not hasattr(t,'sshscriptstack'):
        t.sshscriptstack = SshscriptStack(t)
