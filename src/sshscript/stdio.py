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
import os,traceback,random
try:
    from .errorutils import log_debug
except ImportError:
    from errorutils import log_debug

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
        while self.sessionId == ds.sessionId and not ds.closed:
            if self.timeout is None:
                endtime = None
            else:
                endtime = time.time() + self.timeout
            with ds._condition:
                while not ds._deque:
                    ## threading.Condition().wait(None) would wait forever
                    if not ds._condition.wait(timeout=1.0):
                        ## over 1 second without data
                        if self.sessionId != ds.sessionId:
                            return 
                        elif (endtime is not None) and (time.time() > endtime):
                            if self.silent:
                                return
                            else:
                                raise TimeoutError(f'no data over {self.timeout} seconds')
                if self.sessionId != ds.sessionId:
                    return 
                # Process items in batches to reduce lock contention
                batch = []
                for _ in range(min(100, len(ds._deque))):
                    try:
                        batch.append(ds._deque.popleft())
                    except IndexError:
                        break    
                if batch:
                    try:
                        while os.read(ds._read_fd, 1):
                            pass
                    except BlockingIOError:
                        pass
                    except OSError:
                        pass
                    # Yield each item in the batch
                    for value in batch:
                        yield value
                    if self.timeout is not None:
                        endtime = time.time() + self.timeout
class DequeString(str):
    maxlen = 10000
    sno = 0
    private_attrs = {'_read_fd','_write_fd','_deque', '_lock', '_condition', '_string','append','_listeners','bytes','glue','__add__','__iter__','iter','__call__','__eq__','__str__','__repr__','__radd__','__getitem__','size','__setitem__','__contains__'}    
    def __new__(cls,iterable=None, maxlen=None,bytes=False):
        if iterable is None: iterable = []
        glue = b'' if bytes else ''
        instance = super().__new__(cls, glue.join(iterable))
        return instance    
    def __init__(self, initial=None,maxlen=None,bytes=False):
        '''
        :bytes:
            True: deque would store bytes
            False: deque would store string
        '''
        if maxlen is None: maxlen = self.__class__.maxlen
        self.closed = False
        self.is_bytes = bytes
        self.glue = b'' if self.is_bytes else ''
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
        with self._lock:
            if self.is_bytes:
                return self._string.decode('utf8','ignore')
            else:
                return self._string
    
    def __repr__(self)->str:
        ## f-string would not take return value of this call
        return self._string
    
    def __len__(self)->int:
        return len(self._deque)
    
    def __contains__(self,s):
        ## cation: not same as "in self._string"
        for item in self._deque:
            if s in item: return True
        return False
    
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
        self.callback = callback
        assert pattern is None or isinstance(pattern,str), '"str" pattern supported only'
        self.callback_pattern = pattern

    def append(self, item,splitlines=False):
        """
        Add an item into deque. item could be multiple lines.
        Don't append multiple items, becase
        the reason to put it into list (*items) is that 
        when the listeners does not change the content,
        there is no string-copy , it saves memory usage.
        """
        assert isinstance(item,str),f'{[item]} is not str'
        print('ioooo>>',self.sessionId,[item,self.callback ,self.callback_pattern])
        callback_triggered = self.callback and self.callback_pattern and self.callback_pattern in item
        if callback_triggered:
            item = item.replace(self.callback_pattern,'')
        
        items = [item]
        with self._condition:
            if self._listeners:
                self._listeners[-1](items)
            if splitlines:
                ## contains newline in line
                #print(item.splitlines(True))
                self._deque.extend(items[0].splitlines(True))
            else:
                self._deque.append(items[0])
            try:
                os.write(self._write_fd, b'\x00')
            except BlockingIOError:
                pass  # Ignore if pipe is full
            except OSError as e:
                pass # might be closed (Errno 9)
            else:
                self._condition.notify()
        ## test callback pattern
        if callback_triggered:
            self.callback() 
            ## this is one shot only
            self.callback = None
            self.callback_pattern = None

    def push_listener(self,listener):
        ## listener is callable, called by listener(items)
        self._listeners.append(listener)
    def pop_listener(self,listener):
        assert self._listeners.pop() == listener
    def clear(self):
        self._deque.clear()
        self.sessionId = f'{time.time()}.{random.random()}'
        try:
            if os.get_blocking(self._read_fd):
                os.set_blocking(self._read_fd,False)
                log_debug(f'{"!" * 20} read handle becomes blocking')
            while os.read(self._read_fd, 1):
                pass
        except BlockingIOError:
            pass
        except OSError:
            pass
        except:
            traceback.print_exc()

    def __add__(self, other):
        """Handle ds + other"""
        with self._lock:
            return self._string + other
    
    def __radd__(self, other):
        """Handle other + ds"""
        with self._lock:
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
        assert not self.closed, f'{type(self)} {id(self)}:{self.name}:{self.sessionId} already closed'
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
    stdout = SSHScriptStdout(maxlen=500,bytes=False)
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