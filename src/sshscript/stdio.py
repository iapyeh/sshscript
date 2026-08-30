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
from collections import deque
import time, threading,sys
import os,random
if __package__:
    from .errorutils import get_logger
else:
    from errorutils import get_logger

logger = get_logger()

class DequeStringIter:
    """
    iterating , keep item in deque
    """
    def __init__(self,ds,timeout=None,silent=False):
        """
        :ds:
            instance of DequeString
        :timeout:
            None: wait forever(blocking)
            n: wait for n seconds, then raise TimeoutError if not silent.
        """
        assert isinstance(ds,DequeString)
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
    """
    iterating , popleft item from deque
    """
    def __init__(self,ds,timeout=None,silent=False):
        """
        :timeout:
            None: wait forever(blocking)
            n: wait for n seconds, then raise TimeoutError if not silent.
        """
        assert isinstance(ds,DequeString)
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
        """ watching content for pattern, call callback() when the pattern shows up"""
        assert pattern is None or isinstance(pattern,str), '"str" pattern supported only'
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
        """
        Add an item into deque. item could be multiple lines.
        Don't append multiple items, becase
        the reason to put it into list (*items) is that 
        when the listeners does not change the content,
        there is no string-copy , it saves memory usage.
        """
        assert isinstance(item,str),f'{[item]} is not str'
        #print('ooooo>>',[item])
        callback_to_call = None
        listener_item = item
        with self._condition:
            if self.closed:
                raise IOError('DequeString has closed')
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
        assert self._listeners.pop() == listener
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
        """Handle ds + other"""
        return self._string + other
    
    def __radd__(self, other):
        """Handle other + ds"""
        return other + self._string
            
    def __eq__(self,other):
        return self._string.__eq__(other)

    
    def __call__(self,timeout=None,silent=False,shift=True):
        '''
        by calling this, deque always popleft
        :timeout:
            None: iterate deque and waiting for new item forever(blocking until next data)
            n:int, iterate deque and waiting for new item until without data for n seconds
        :silent:
            True: do not raise TimeoutError 
            False: raise TimeoutError
        :shift:
            True: popleft item from deque once yielded
            False: keep item in deque
        usage example:
            for line in stdout(None):
                ... return current item of deque , popleft item
            for line in stdout():
                ... blocking for ever, popleft item
            for line in stdout(3):
                ... return current item of deque,popleft item, then, wait for next itme in 3 seconds, if not reaise TimeoutEror
            for line in stdout(3,silent=True):
                ... return current item of deque,popleft item, then, wait for next itme in 3 seconds, if not exit the loop
        '''
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

def unittest():
    stdout = SSHScriptStdout(maxlen=500)
    assert not stdout,'stdout is empty but with True value'
    def setvalue():
        stdout.append('that')
        stdout.append('is')
        stdout.append('an')
        stdout.append('book')
    setvalue()
    assert stdout,'stdout is not empty but with False value'
    stdout[0] = 'this'
    assert 'this' in stdout
    assert stdout[1] == 'is', f'it is {[stdout[1]]}'
    assert stdout == 'thisisanbook',f'it is {[stdout]}'
    assert 'thisisanbook' == stdout,f'it is {[stdout]}'
    assert ','.join(stdout) == 'this,is,an,book',f'it is {[",".join(stdout)]}'
    assert stdout + 'ok' == 'thisisanbookok',f'it is {["ok"+stdout]}'
    assert 'ok' + stdout == 'okthisisanbook',f'it is {["ok"+stdout]}'
    assert stdout.strip() == 'thisisanbook',f'it is {[stdout]}'
    assert stdout.join(['-']) == '-',f'it is {[stdout.join(["-"])]}'
    assert stdout.join(['-','-']) == '-thisisanbook-',f'it is {[stdout.join(["-","-"])]}'
    assert len(stdout) == 4,f'it is {len(stdout)}'

    def adding():
        import random
        for i in range(3):
            time.sleep(1)
            stdout.append(str(random.randint(100,200)))    
    def dump():
        print('dumping start')
        for i in range(2):
            if i==0:
                # this; is; a; book
                # stdout does not consumed
                for c in stdout:
                    print([i,c])
                    assert len(c) > 1
                assert stdout == 'thisisanbook',f'it is {[stdout]}'

            else:
                t1 = threading.Thread(target=adding,no_patch=True)
                t1.start()
                for c in stdout(3,True):
                    print(['timeout=3',i,c])
                t1.join()
                assert stdout == '',f'it is {[stdout]}'
    t0 = threading.Thread(target=dump,no_patch=True)
    t0.start()
    t0.join()
if __name__ == '__main__':
    unittest()
