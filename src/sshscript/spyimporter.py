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

## 2025/3/3
## v2.0.3 feature: import *.spy file directly
"""Explicit, reference-counted support for importing .spy modules and packages."""

import importlib.abc
import importlib.util
import os
import sys
import threading
from contextlib import contextmanager

if __package__:
    from . import dollarparser
    from . import patching
    from .dollar import Dollar
else:
    import dollarparser
    import patching
    from dollar import Dollar

class SpyLoader(importlib.abc.Loader):
    """Compile and execute .spy modules while preserving their original source locations."""
    
    def __init__(self, path, package):
        self.path = path
        self.package = package

    def create_module(self, spec):
        return None  # Use the default module creation process

    def exec_module(self, module):
        """Execute compiled .spy source in the module namespace."""
        with open(self.path, "r", encoding="utf-8") as file:
            original_code = file.read()

        ## So, for a module located in foo/bar/baz.py, __name__ is set to 
        ## foo.bar.baz, and __package__ is set to foo.bar,
        ## while foo/bar/__init__.py will have foo.bar for both the __name__ 
        ## and __package__ attributes. (Martijn Pieters on stackoverflow)
        g = {
            "__name__": module.__name__,
            "__package__":self.package,
            "__file__": self.path,
            "Dollar": Dollar,
            "sys": sys,
            "threading": threading,
            "patching": patching,
            "_sshscript_session_": None,
        }
        stack = patching.peek_thread_stack()
        if stack is not None and len(stack):
            g["_sshscript_session_"] = stack[-1]
        module.__dict__.update(g)
        code = dollarparser.compile_spy(self.path, original_code)
        exec(code, module.__dict__)  # Run the modified code inside the module's namespace


class SpyFileFinder(importlib.abc.MetaPathFinder):
    """Find .spy modules and packages through Python's import machinery."""

    def find_spec(self, fullname, path=None, target=None):
        if path is None:
            path = sys.path  # Search in sys.path        
        fullname_file = fullname.rsplit('.', 1)[-1]
        for entry in path:
            if not os.path.isdir(entry):
                continue
            spy_init_file = os.path.join(
                entry,
                fullname_file,
                '__init__.spy',
            )
            if os.path.isfile(spy_init_file):
                package = fullname
                loader = SpyLoader(spy_init_file, package)
                spec = importlib.util.spec_from_loader(
                    fullname,
                    loader,
                    origin=spy_init_file,
                    is_package=True,
                )
                spec.submodule_search_locations = [
                    os.path.join(entry, fullname_file)
                ]
                return spec
            else:
                spy_file = os.path.join(entry, fullname_file + '.spy')
                if os.path.isfile(spy_file):
                    package = fullname.rpartition('.')[0]
                    loader = SpyLoader(spy_file, package)
                    return importlib.util.spec_from_loader(
                        fullname,
                        loader,
                        origin=spy_file,
                    )
        return None  # Module not found

_spy_finder = SpyFileFinder()
_registration_lock = threading.RLock()
_registration_count = 0
_remove_when_unused = False


def register_spy_importer():
    """Register the ``.spy`` finder once and return it."""
    global _registration_count, _remove_when_unused
    with _registration_lock:
        if _registration_count == 0:
            _remove_when_unused = _spy_finder not in sys.meta_path
        if _remove_when_unused and _spy_finder not in sys.meta_path:
            sys.meta_path.insert(0, _spy_finder)
        _registration_count += 1
    return _spy_finder


def unregister_spy_importer():
    """Release one registration and remove the finder when no user remains."""
    global _registration_count, _remove_when_unused
    with _registration_lock:
        if _registration_count == 0:
            return
        _registration_count -= 1
        if _registration_count == 0 and _remove_when_unused:
            while _spy_finder in sys.meta_path:
                sys.meta_path.remove(_spy_finder)
            _remove_when_unused = False


@contextmanager
def spy_imports():
    """Temporarily enable Python imports of .spy modules and packages.

    Use with spy_imports(): before an import in ordinary Python. Registration
    is reference-counted so nested/overlapping contexts retain the finder until
    the last user exits. Imported modules remain cached in sys.modules.
    """
    register_spy_importer()
    try:
        yield
    finally:
        unregister_spy_importer()
