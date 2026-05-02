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
import importlib.abc
import importlib.util
import sys,os,atexit
import dollarparser 
from errorutils import dumpScript
from dollar import Dollar

temp_files = []
def cleanup():
    for file_path in temp_files:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error removing {file_path}: {e}")
    temp_files.clear()  # Reset the list
# Register the cleanup function for normal exit
atexit.register(cleanup)

class SpyLoader(importlib.abc.Loader):
    """Custom loader to load and modify .spy files before execution."""
    
    def __init__(self, path, package):
        self.path = path
        self.package = package

    def modify_source_code(self, source_code):
        """Modify the source code before execution."""
        return 'import sys,threading\n' + dollarparser.convert(self.path,source_code)

    def create_module(self, spec):
        """Create a module (default implementation)."""
        return None  # Use the default module creation process

    def exec_module(self, module):
        """Execute the module with modified code."""
        with open(self.path, "r", encoding="utf-8") as file:
            original_code = file.read()

        modified_code = self.modify_source_code(original_code)

        ## write a tempory file for correctly report error in traceback infomation
        if not os.path.exists(os.path.join(os.path.dirname(self.path),'__pycache__')):
            os.mkdir(os.path.join(os.path.dirname(self.path),'__pycache__'))
        modified_path = os.path.join(os.path.dirname(self.path),'__pycache__',os.path.basename(self.path))
        with open(modified_path,'w') as fd:
            fd.write(modified_code)
        temp_files.append(modified_path)

        ## So, for a module located in foo/bar/baz.py, __name__ is set to 
        ## foo.bar.baz, and __package__ is set to foo.bar,
        ## while foo/bar/__init__.py will have foo.bar for both the __name__ 
        ## and __package__ attributes. (Martijn Pieters on stackoverflow)
        g = {
            "__name__": module.__name__,
            "__package__":self.package,
            "__file__": self.path,
            "Dollar": Dollar,
        }
        module.__dict__.update(g)
        code = compile(modified_code, modified_path, 'exec')
        try:
            exec(code, module.__dict__)  # Run the modified code inside the module's namespace
        except SyntaxError as e:
            print(f'#file:{self.path}')
            dumpScript( modified_code )
            raise   
## hook the loader 
import importlib.machinery
package_path = {}
class SpyFileFinder(importlib.machinery.FileFinder):
    """Custom file finder for .spy files."""

    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        """Find the module spec for a .spy file."""
        if path is None:
            path = sys.path  # Search in sys.path        
        if '.' in fullname:
            ## remove 1st item from fullname, if it is in format of "A.B"
            fullname_file = fullname.split('.')[-1]
        else:
            fullname_file = fullname
        #print('   >> fullname=',fullname)
        for entry in path:
            if not os.path.isdir(entry): continue
            spy_init_file = os.path.join(entry,fullname_file,'__init__.spy')
            if os.path.exists(spy_init_file):
                package = fullname
                with open(spy_init_file, "r"): 
                    loader = SpyLoader(spy_init_file,package)
                    m = importlib.util.spec_from_loader(fullname, loader,origin=spy_init_file,is_package=package)
                    m.submodule_search_locations = [os.path.join(entry,fullname_file)]
                    return m
            else:
                spy_file = os.path.join(entry,fullname_file+'.spy')
                if os.path.exists(spy_file):
                    with open(spy_file, "r"):
                        package = '.'.join(fullname.split('.')[:-1])
                        loader = SpyLoader(spy_file,package)
                        return importlib.util.spec_from_loader(fullname, loader,origin=spy_file)
        return None  # Module not found

def register_spy_importer():
    """Register the .spy importer."""
    sys.meta_path.insert(0, SpyFileFinder)  # Insert at the beginning to check .spy first

# Call this function once at the start of your program
register_spy_importer()