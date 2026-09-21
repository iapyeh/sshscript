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

##
## iteratable stdout, stderr objects
##
"""Live command output buffers with string access and optional consuming iteration."""

from collections import deque
import time, threading,sys
import os,random
if __package__:
    from .errorutils import get_logger
else:
    from errorutils import get_logger

logger = get_logger()

class DequeStringIter:
    """Iterate buffered chunks and wait for new output without consuming chunks."""
    def __init__(self,ds,timeout=None,silent=False):
        """Bind a buffer; timeout=None waits indefinitely, silent suppresses timeout errors."""
        if not isinstance(ds,DequeString):
            raise TypeError('ds must be DequeString')
        self.ds = ds
        self.sessionId = ds.sessionId
        self.timeout = timeout
        self.silent = silent
    def __iter__(self):
        pos = 0
        ds = self.ds
        if self.timeout is None:
            endtime = None
        else:
            endtime = time.time() + self.timeout
        while self.sessionId == ds.sessionId and not ds.closed:
            with ds._condition:
                while len(ds._deque) <= pos:
                    ## threading.Condition().wait(None) would wait forever
                    if ds._condition.wait(timeout=1.0):
                        break
                    else:
                        ## firstly, check if self.clear() was called during waiting
                        if self.sessionId != ds.sessionId: return 
                        elif (endtime is not None) and (time.time() > endtime):
                            if self.silent:
                                #print(f'{type(self)} {id(self)}:{self.sessionId} iter silent timeout')  
                                return
                            else:
                                raise TimeoutError(f'no data over {self.timeout} seconds')
                
                if self.sessionId != ds.sessionId: return 
                # Process items in batches to reduce lock contention
                batch = []
                for i in range(pos,len(ds._deque)):
                    try:
                        batch.append(ds._deque[i])
                    except IndexError:
                        break
                    else:
                        pos += 1
                if batch:
                    try:
                        while os.read(ds._read_fd, 1):
                            pass
                    except BlockingIOError:
                        pass
                    except OSError:
                        ## errno=9, closed
                        pass
                    # Yield each item in the batch
                    for value in batch:
                        yield value        
                    if self.timeout is not None:
                        endtime = time.time() + self.timeout
class DequeStringPopleftIter:
    """Iterate and consume buffered chunks, waiting for new output as configured."""
    def __init__(self,ds,timeout=None,silent=False):
        """Bind a buffer; timeout=None waits indefinitely, silent suppresses timeout errors."""
        if not isinstance(ds,DequeString):
            raise TypeError('ds must be DequeString')
        self.ds = ds
        self.timeout = timeout
        self.silent = silent
        self.sessionId = ds.sessionId
    def __iter__(self):
        ds = self.ds
        ## set initial value of endtime
        if self.timeout is None:
            endtime = None
        else:
            endtime = time.time() + self.timeout
        while self.sessionId == ds.sessionId and not ds.closed:
            if endtime is not None and time.time() > endtime:
                if self.silent:
                    break
                else:
                    raise TimeoutError(f'no data over {self.timeout} seconds')

            count = len(ds._deque)
            if count == 0:
                time.sleep(0.1)
                continue
            ## yield values
            with ds._condition:
                for _ in range(count):
                    try:
                        yield ds._deque.popleft()
                        ds._condition.wait(timeout=0.1)
                    except IndexError:
                        break
                ## reset timeout
                if self.timeout is not None:
                    endtime = time.time() + self.timeout

class DequeString(str):
    """Live output buffer with a string interface over stored text chunks.

    str(buffer) takes a snapshot of the current text. Plain iteration visits
    stored chunks without consuming them or waiting for future output;
    buffer(timeout, silent, shift) creates an iterator that can wait for more.
    Chunks are not guaranteed to be complete lines. len(buffer) counts chunks,
    not characters. Use a string snapshot for ordinary immutable string behavior.
    """
    maxlen = 10000
    sno = 0
    private_attrs = {
        '_read_fd', '_write_fd', '_deque', '_lock', '_condition',
        '_string', 'append', '_listeners', 'glue', '__add__', '__iter__',
        'iter', '__call__', '__eq__', '__str__', '__repr__', '__radd__',
        '__getitem__', 'size', '__setitem__', '__contains__', 'splitlines',
    }
    def __new__(cls,initial=None, maxlen=None):
        initial = ''.join([str(x) for x in initial]) if initial else None
        value = "" if initial is None else str(initial)  
        return super().__new__(cls, value)
    def __init__(self, initial=None,maxlen=None):
        if maxlen is None: maxlen = self.__class__.maxlen
        self.closed = False
        self.glue = ''
        DequeString.sno += 1
        self.name = f'DS{DequeString.sno}'
        self.iterTimeout = None
        self.iterTimeoutSilent = False

        
        if initial is None:
            self._deque = deque(maxlen=maxlen)
        ## isinstance(initial, DequeString) should be in front of isinstance(initial, str) 
        elif isinstance(initial, DequeString):
            self._deque = initial._deque.copy()
        elif isinstance(initial, str):
            self._deque = deque(maxlen=maxlen)
            self._deque.append(initial)
        else:
            raise ValueError('initial value should be string')
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        

        ## Create a pipe for select() compatibility
        self._read_fd, self._write_fd = os.pipe()
        ## Set non-blocking mode (optional, for cleaner handling)
        os.set_blocking(self._read_fd, False)
        os.set_blocking(self._write_fd, False)
        ## reset for every refresh()
        ## for non-popleft iteration(see SSHScriptStderr.iter())
        self.sessionId = f'{time.time()}.{random.random()}'
        self._listeners = []

        ## this is one shot only
        self.callback_pattern = None
        self.callback = None
    @property
    def _string(self)->str:
        with self._condition:
            try:
                return self.glue.join(self._deque)
            except TypeError:
                #return str(f'{type(self)} {id(self)}:{self.sessionId}')
                return str(self._deque)

    def __getitem__(self, idx):
        return self._deque.__getitem__(idx)
    
    def __setitem__(self, idx, value):
        return self._deque.__setitem__(idx,value)
    
    def size(self):
        ## when getting value by slice (eg. self[1]),
        ## call size() to get length of deque
        return len(self._deque)

    def __str__(self)->str:
        ## f-string would take return value of this call
        return self._string
    
    def __repr__(self)->str:
        ## f-string would not take return value of this call
        return self._string
    
    def __len__(self)->int:
        return len(self._deque)
    
    def __contains__(self,s):
        ## cation: not same as "in self._string"
        return s in self._string

    def splitlines(self, keepends=False):
        """Split the latest buffered content, not the immutable str base value.

        DequeString is a live buffer implemented as a str subclass.  Delegating
        this method through __getattribute__ binds it to a snapshot too early,
        which can miss output appended between attribute lookup and invocation.
        """
        return self._string.splitlines(keepends)
    
    def __getattribute__(self, name):
        # Allow access to private attributes directly
        if name in DequeString.private_attrs:
            return object.__getattribute__(self, name)
        elif name in dir(str) and not name.startswith('_'):
            return getattr(object.__getattribute__(self, '_string'), name)
        # Delegate deque methods
        #if name in dir(deque) and not name.startswith('_'):
        #    return getattr(object.__getattribute__(self, '_deque'), name)
        # Delegate string methods
        else:
            return object.__getattribute__(self, name)

    def set_callback(self,callback,pattern):
        """Watch for a pattern in appended output and invoke its callback when found."""
        if not (pattern is None or isinstance(pattern,str)):
            raise TypeError('pattern must be str or None')
        with self._condition:
            self.callback = callback
            self.callback_pattern = pattern

    def _remove_string_range(self, start, end):
        """Remove a character range while preserving the deque chunk layout."""
        position = 0
        retained = []
        for chunk in self._deque:
            chunk_end = position + len(chunk)
            if chunk_end <= start or position >= end:
                retained.append(chunk)
            else:
                left = chunk[:max(0, start - position)]
                right = chunk[max(0, end - position):]
                if left or right:
                    retained.append(left + right)
            position = chunk_end

        self._deque.clear()
        self._deque.extend(retained)

    def append(self, item,splitlines=False):
        """Append incoming text and notify listeners.

        A callback marker may span chunks: remove the matched marker and invoke
        its callback once, outside the buffer lock. Notify the top listener and
        waiting readers about the appended output.
        """
        if not isinstance(item,str):
            raise TypeError('appended output must be str')
        #print('ooooo>>',[item])
        callback_to_call = None
        listener_item = item
        with self._condition:
            if self.closed:
                raise BrokenPipeError('DequeString has closed')
            if splitlines:
                ## contains newline in line
                self._deque.extend(item.splitlines(True))
            else:
                self._deque.append(item)

            callback = self.callback
            pattern = self.callback_pattern
            if callback and pattern:
                content = self.glue.join(self._deque)
                match_start = content.find(pattern)
                if match_start >= 0:
                    match_end = match_start + len(pattern)
                    self._remove_string_range(match_start, match_end)
                    callback_to_call = callback
                    # Keep listener behavior compatible when the whole prompt
                    # happened to arrive in this append call.
                    listener_item = item.replace(pattern, '')
                    self.callback = None
                    self.callback_pattern = None

            ## Caution: only the top listener was called
            if len(self._listeners):
                self._listeners[-1](listener_item)

            try:
                os.write(self._write_fd, b'\x00')
            except BlockingIOError:
                pass  # Ignore if pipe is full
            except OSError as e:
                pass # might be closed (Errno 9)
            else:
                self._condition.notify()

        ## test callback pattern
        if callback_to_call is not None:
            try:
                callback_to_call()
            except TypeError:
                ## Preserve the historical one-shot callback behavior.
                pass

    def push_listener(self,listener):
        ## listener is callable, called by listener(items)
        with self._condition:
            listener(self.glue.join(self._deque))
            self._listeners.append(listener)
    def pop_listener(self,listener):
        with self._condition:
            if not self._listeners:
                raise RuntimeError('listener stack is empty')
            if self._listeners[-1] is not listener:
                raise RuntimeError('listener is not on top of stack')
            self._listeners.pop()
    def clear(self):
        self._deque.clear()
        self.sessionId = f'{time.time()}.{random.random()}'
        try:
            if os.get_blocking(self._read_fd):
                os.set_blocking(self._read_fd,False)
                logger.debug(
                    'Read descriptor was blocking; switched to non-blocking mode '
                    '(fd=%s)',
                    self._read_fd,
                )
            while os.read(self._read_fd, 1):
                pass
        except BlockingIOError:
            pass
        except OSError:
            pass

    def __add__(self, other):
        return self._string + other
    
    def __radd__(self, other):
        return other + self._string
            
    def __eq__(self,other):
        return self._string.__eq__(other)

    
    def __call__(self,timeout=None,silent=False,shift=True):
        """Iterate chunks, waiting for new output until timeout or buffer closure/reset.

        shift=True consumes yielded chunks; False retains them. timeout=None waits
        indefinitely; a number limits idle waiting for new output. silent=True ends
        iteration on timeout, otherwise TimeoutError is raised.

        Example::

            for chunk in stdout(3, silent=True):
                print(chunk, end="")
        """
        if shift:
            return DequeStringPopleftIter(self,timeout,silent)
        else:
            return DequeStringIter(self,timeout,silent)    


    def __iter__(self):
        yield from self._deque

    def shift(self):
        ## aka "popleft"
        with self._condition:
            return self._deque.popleft()
    def pop(self):
        with self._condition:
            return self._deque.pop()

    def fileno(self):
        """Return the read end of the pipe as a file descriptor for select()"""
        return self._read_fd    

    def close(self):
        """Clean up pipe file descriptors"""
        #assert not self.closed, f'{type(self)} {id(self)}:{self.name}:{self.sessionId} already closed'
        with self._condition:
            if self.closed: return
            self.closed = True
            try:
                os.close(self._write_fd)
            except OSError:
                pass
            try:
                os.close(self._read_fd)
            except OSError:
                pass
    def __del__(self):
        if not self.closed: self.close()

class SSHScriptStdout(DequeString):
    maxlen = 10000

class SSHScriptStderr(DequeString):
    maxlen = 10000
