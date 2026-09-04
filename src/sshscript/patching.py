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
# Per-thread execution state owned by SSHScript, without patching Thread.
import functools
import threading
import weakref
from collections import deque


_thread_stacks = weakref.WeakKeyDictionary()
_thread_stacks_lock = threading.RLock()


class SshscriptStack(object):
    """
    A stack-like data structure that maintains a thread-safe collection of SSH session objects.
    
    This class implements a stack with a maximum length limit and provides methods
    for managing SSH sessions within a thread context. It maintains a history of
    sessions and allows for session management operations.
    
    Attributes:
        stack (deque): The main storage container for session objects
        owner_id (int): Identity of the thread that owns this stack instance
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
        self.owner_id = id(owner)
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

    def snapshot(self):
        """Return a stable copy suitable for inheritance by a new thread."""
        with self.locker:
            return list(self.stack)

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
        with self.locker:
            if not self.stack:
                raise IndexError('cannot pop an empty SSHScript stack')
            if x is not None and self.stack[-1] is not x:
                raise RuntimeError(
                    f'{self.owner_id}:{x} is not on top of ({self.stack})'
                )
            return self.stack.pop()

    def discard(self, item):
        """Remove the most recent identical item, regardless of its position."""
        with self.locker:
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index] is item:
                    del self.stack[index]
                    return True
        return False
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

    def connect_and_activate(self, *args, **kwargs):
        """Connect and make the new session active until it is closed."""
        session = self.connect(*args, **kwargs)
        session._attach_to_thread_stack(self)
        return session

    def close(self):
        """
        Close the session at the top of the stack.
        
        Returns:
            The result of closing the session
        """
        session = self[-1]
        result = session.close()
        if len(self) and self[-1] is session:
            self.pop(session)
        return result
def get_thread_stack(thread=None, initial_session=None):
    """Return SSHScript's stack for a thread, creating it on first use.

    SSHScript owns the weak registry; neither importing nor executing it adds
    private attributes to application ``threading.Thread`` objects.
    """
    thread = thread or threading.current_thread()
    with _thread_stacks_lock:
        stack = _thread_stacks.get(thread)
        if stack is None:
            initialitems = (
                [initial_session] if initial_session is not None else None
            )
            stack = SshscriptStack(thread, initialitems)
            _thread_stacks[thread] = stack
        elif initial_session is not None and len(stack) == 0:
            stack.append(initial_session)
        return stack


def peek_thread_stack(thread=None):
    """Return an existing stack without creating process-visible state."""
    thread = thread or threading.current_thread()
    with _thread_stacks_lock:
        return _thread_stacks.get(thread)


def set_thread_stack(stack, thread=None):
    """Associate an existing stack with a thread for an explicit script run."""
    thread = thread or threading.current_thread()
    with _thread_stacks_lock:
        _thread_stacks[thread] = stack
    return stack


def clear_thread_stack(thread=None):
    """Forget a thread's execution stack after its target has finished."""
    thread = thread or threading.current_thread()
    with _thread_stacks_lock:
        return _thread_stacks.pop(thread, None)


def context_thread(
    group=None,
    target=None,
    name=None,
    args=(),
    kwargs=None,
    *,
    daemon=None,
):
    """Construct a standard Thread that inherits the caller's SSHScript stack."""
    parent_stack = peek_thread_stack()
    initial_stack = (
        parent_stack.snapshot() if parent_stack is not None else []
    )

    if target is None:
        wrapped_target = None
    else:
        @functools.wraps(target)
        def wrapped_target(*target_args, **target_kwargs):
            stack = SshscriptStack(
                threading.current_thread(),
                initial_stack,
            )
            set_thread_stack(stack)
            try:
                return target(*target_args, **target_kwargs)
            finally:
                clear_thread_stack()

    return threading.Thread(
        group=group,
        target=wrapped_target,
        name=name,
        args=args,
        kwargs=kwargs,
        daemon=daemon,
    )
