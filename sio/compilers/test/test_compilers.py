from nose.tools import eq_

from sio.compilers.job import run
from sio.workers import ft
from sio.workers.execute import execute
from filetracker.dummy import DummyClient

import glob
import os.path
import shutil
import stat

# sio2-compilers tests
#
# Source files used for testing are located in
# sources/ directory
#
# A few notes:
#
# 1) This module uses test generators intensely. This
#    approach makes adding tests for new compilers a breeze.
#    For more details about this technique, see:
# http://readthedocs.org/docs/nose/en/latest/writing_tests.html#test-generators
#
# 2) By default, sandboxed compilers are excluded from the
#    testing, due to their rather unwieldy dependencies. You
#    can enable them by turning ENABLE_SANDBOXED_COMPILERS on.
#    All needed dependencies will be downloaded automagically
#    by sio.workers.sandbox.
#

SOURCES = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sources')
ENABLE_SANDBOXED_COMPILERS = False

class TemporaryCwd(object):
    "Helper class for changing the working directory."

    def __init__(self):
        self.path = os.tmpnam()

    def __enter__(self):
        os.mkdir(self.path)
        self.previousCwd = os.getcwd()
        os.chdir(self.path)

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        os.chdir(self.previousCwd)
        shutil.rmtree(self.path)

def upload_files():
    "Uploads all files from SOURCES to a newly created dummy filetracker"

    # DummyClient operates in the working directory.
    ft.set_instance(DummyClient())
    for path in glob.glob(os.path.join(SOURCES, '*')):
        ft.upload({'path': '/' + os.path.basename(path)}, 'path', path)

def compile_and_run(compiler_env, expected_output):
    """Helper function for compiling, launching and
       testing the result of a program.
    """

    run(compiler_env)

    binary = ft.download({'path': '/out'}, 'path')

    os.chmod(binary, stat.S_IXUSR)

    retcode, output = execute(['./' + binary])
    eq_(retcode, 0)
    eq_(output.strip(), expected_output)

    os.remove(binary)

def test_compilation():
    def _test(message, compiler, source):
        with TemporaryCwd():
            upload_files()
            compile_and_run({
                'source_file': source,
                'compiler': compiler,
                'out_file': '/out',
                }, message)

    yield _test, 'Hello World from c', 'system-c', '/simple.c'
    yield _test, 'Hello World from cpp', 'system-cpp', '/simple.cpp'
    yield _test, 'Hello World from pas', 'system-pas', '/simple.pas'

    if ENABLE_SANDBOXED_COMPILERS:
        yield _test, 'Hello World from c', 'default-c', '/simple.c'
        yield _test, 'Hello World from cpp', 'default-cpp', '/simple.cpp'
        yield _test, 'Hello World from pas', 'default-pas', '/simple.pas'

def test_compilation_with_additional_library():
    def _test(message, compiler, source, sources, includes = ()):
        with TemporaryCwd():
            upload_files()

            compile_and_run({
                    'source_file': source,
                    'additional_includes': includes,
                    'additional_sources': sources,
                    'compiler': compiler,
                    'out_file': '/out',
                    }, message)

    yield _test, 'Hello World from c-lib', 'system-c', '/simple-lib.c',\
          '/library.c', '/library.h'
    yield _test, 'Hello World from cpp-lib', 'system-cpp', '/simple-lib.cpp',\
          '/library.cpp', '/library.h'
    yield _test, 'Hello World from pas-lib', 'system-pas', '/simple-lib.pas',\
          '/pas_library.pas'

    if ENABLE_SANDBOXED_COMPILERS:
        yield _test, 'Hello World from c-lib', 'default-c',\
              '/simple-lib.c', '/library.c', '/library.h'
        yield _test, 'Hello World from cpp-lib', 'default-cpp',\
              '/simple-lib.cpp', '/library.cpp', '/library.h'
        yield _test, 'Hello World from pas-lib', 'default-pas',\
              '/simple-lib.pas', '/pas_library.pas'

def test_compilation_with_additional_library_and_dictionary_params():
    def _test(message, compiler, source):
        with TemporaryCwd():
            upload_files()

            compile_and_run({
                    'source_file': source,
                    'additional_includes': {
                        'c': '/library.h',
                        'cpp': '/library.h',
                        },
                    'additional_sources': {
                        'c': '/library.c',
                        'cpp': '/library.cpp',
                        'pas': '/pas_library.pas',
                        },
                    'compiler': compiler,
                    'out_file': '/out',
                    }, message)

    yield _test, 'Hello World from c-lib', 'system-c', '/simple-lib.c'
    yield _test, 'Hello World from cpp-lib', 'system-cpp', '/simple-lib.cpp'
    yield _test, 'Hello World from pas-lib', 'system-pas', '/simple-lib.pas'

    if ENABLE_SANDBOXED_COMPILERS:
        yield _test, 'Hello World from c-lib', 'default-c',\
              '/simple-lib.c'
        yield _test, 'Hello World from cpp-lib', 'default-cpp',\
              '/simple-lib.cpp'
        yield _test, 'Hello World from pas-lib', 'default-pas',\
              '/simple-lib.pas'

