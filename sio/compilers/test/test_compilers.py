import glob
import os.path
import shutil
import stat
import sys

from nose.tools import ok_, eq_, timed

from sio.compilers.job import run
from sio.workers import ft
from filetracker.dummy import DummyClient
from sio.compilers.common import DEFAULT_COMPILER_OUTPUT_LIMIT, \
        DEFAULT_COMPILER_TIME_LIMIT, DEFAULT_COMPILER_MEM_LIMIT
from sio.workers.executors import UnprotectedExecutor, PRootExecutor
from sio.workers.file_runners import get_file_runner

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
#    can enable them by setting environment variable TEST_SANDBOXES to 1.
#    All needed dependencies will be downloaded automagically
#    by sio.workers.sandbox.
#

SOURCES = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sources')
ENABLE_SANDBOXED_COMPILERS = os.environ.get('TEST_SANDBOXES', False)


def in_(a, b, msg=None):
    """Shorthand for 'assert a in b, "%r not in %r" % (a, b)"""
    if a not in b:
        raise AssertionError(msg or "%r not in %r" % (a, b))


class TemporaryCwd(object):
    "Helper class for changing the working directory."

    def __init__(self, inner_directory=None):
        self.temp_directory = os.tmpnam()
        if inner_directory:
            self.path = os.path.join(self.temp_directory, inner_directory)
        else:
            self.path = self.temp_directory

    def __enter__(self):
        os.makedirs(self.path)
        self.previousCwd = os.getcwd()
        os.chdir(self.path)

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        os.chdir(self.previousCwd)
        shutil.rmtree(self.temp_directory)

def upload_files():
    "Uploads all files from SOURCES to a newly created dummy filetracker"

    # DummyClient operates in the working directory.
    ft.set_instance(DummyClient())
    for path in glob.glob(os.path.join(SOURCES, '*')):
        ft.upload({'path': '/' + os.path.basename(path)}, 'path', path)

def print_env(env):
    from pprint import pprint
    pprint(env)

def compile_and_run(compiler_env, expected_output, program_args=None):
    """Helper function for compiling, launching and
       testing the result of a program.
    """

    # Dummy sandbox doesn't support asking for versioned filename
    out_file = compiler_env['out_file']
    result_env = run(compiler_env)
    print_env(result_env)

    eq_(result_env['result_code'], 'OK')
    binary = ft.download({'path': out_file}, 'path')

    os.chmod(binary, stat.S_IXUSR | os.stat(binary).st_mode)

    if not program_args:
        program_args = []

    executor = UnprotectedExecutor()
    frkwargs = {}

    # Hack for java
    if compiler_env.get('compiler') == 'default-java':
        executor = PRootExecutor('compiler-java.1_8')
        frkwargs['proot_options'] = ['-b', '/proc']
        frkwargs['time_limit'] = 90000

    frunner = get_file_runner(executor, result_env)
    with frunner:
        renv = frunner(binary, program_args,
                       stderr=sys.__stderr__, capture_output=True, **frkwargs)
    eq_(renv['return_code'], 0)
    eq_(renv['stdout'].strip(), expected_output)

    os.remove(binary)

def test_compilation():
    def _test(message, compiler, source, program_args=None):
        with TemporaryCwd():
            upload_files()
            compile_and_run({
                'source_file': source,
                'compiler': compiler,
                'out_file': '/out',
                }, message, program_args)

    compilers = ['system-']
    if ENABLE_SANDBOXED_COMPILERS:
        compilers += ['default-']

    for compiler in compilers:
        yield _test, 'Hello World from c', compiler + 'c', '/simple.c'
        yield _test, '6.907167, 31.613478, 1.569796', compiler + 'c', \
                '/libm.c', ['999.412']
        yield _test, 'Hello World from cpp', compiler + 'cpp', '/simple.cpp'
        yield _test, 'Hello World from cc', compiler + 'cc', '/simple.cc'
        yield _test, '3\n5\n5\n7\n9\n10', compiler + 'cpp', '/libstdc++.cpp'
        yield _test, 'Hello World from pas', compiler + 'pas', '/simple.pas'
        yield _test, 'Hello World from java', compiler + 'java', '/simple.java'

    if ENABLE_SANDBOXED_COMPILERS:
        yield _test, '12903', 'default-cpp', '/cpp11.cpp'

def test_compilation_with_additional_library():
    def _test(message, compiler, source, sources, includes=()):
        with TemporaryCwd():
            upload_files()

            compile_and_run({
                    'source_file': source,
                    'additional_includes': includes,
                    'additional_sources': sources,
                    'compiler': compiler,
                    'out_file': '/out',
                    }, message)

    compilers = ['system-']
    if ENABLE_SANDBOXED_COMPILERS:
        compilers += ['default-']

    for compiler in compilers:
        yield _test, 'Hello World from c-lib', compiler + 'c', \
              '/simple-lib.c', '/library.c', '/library.h'
        yield _test, 'Hello World from cpp-lib', compiler + 'cpp', \
              '/simple-lib.cpp', '/library.cpp', '/library.h'
        yield _test, 'Hello World from pas-lib', compiler + 'pas', \
              '/simple-lib.pas', '/pas_library.pas'
        yield _test, 'Hello World from java-lib', compiler + 'java', \
                '/simple_lib.java', '/library.java'

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
                        'java': '/library.java',
                        },
                    'compiler': compiler,
                    'out_file': '/out',
                    }, message)

    compilers = ['system-']
    if ENABLE_SANDBOXED_COMPILERS:
        compilers += ['default-']

    for compiler in compilers:
        yield _test, 'Hello World from c-lib', compiler + 'c', '/simple-lib.c'
        yield _test, 'Hello World from cpp-lib', compiler + 'cpp', \
            '/simple-lib.cpp'
        yield _test, 'Hello World from pas-lib', compiler + 'pas', \
            '/simple-lib.pas'
        yield _test, 'Hello World from java-lib', compiler + 'java', \
            '/simple_lib.java'


def test_compilation_with_additional_archive():
    def _test(message, compiler, source, sources, archive, unexpected_files):
        with TemporaryCwd(inner_directory='one_more_level'):
            upload_files()

            compile_and_run({
                    'source_file': source,
                    'additional_sources': sources,
                    'additional_archive': archive,
                    'compiler': compiler,
                    'out_file': '/out',
                    }, message)

            for f in unexpected_files:
                ok_(not os.path.exists(f))


    yield _test, 'Hello World from c-lib', 'system-c', '/simple-lib.c', \
          '/library.c', '/library-archive.zip', ['../b.txt']

    if ENABLE_SANDBOXED_COMPILERS:
        yield _test, 'Hello World from c-lib', 'default-c', \
              '/simple-lib.c', '/library.c', '/library-archive.zip', \
              ['../b.txt']


COMPILATION_OUTPUT_LIMIT = 100  # in bytes
COMPILATION_RESULT_SIZE_LIMIT = 5 * 1024 * 1024  # in bytes

def compile_fail(compiler_env, expected_in_compiler_output=None):
    """Helper function for compiling and asserting that it fails."""

    result_env = run(compiler_env)
    print_env(result_env)

    eq_(result_env['result_code'], 'CE')

    if 'compilation_output_limit' not in  compiler_env:
        ok_(len(result_env['compiler_output']) <=
                DEFAULT_COMPILER_OUTPUT_LIMIT)
    elif compiler_env['compilation_output_limit'] is not None:
        ok_(len(result_env['compiler_output']) <=
                compiler_env['compilation_output_limit'])

    if expected_in_compiler_output:
        in_(expected_in_compiler_output, result_env['compiler_output'])

    return result_env

# Test with overly-limited resources
def test_compilation_error_gcc(mem_limit=128, time_limit=2000):
    time_hard_limit = 3 * time_limit
    @timed(time_hard_limit * 1.1)
    def _test_size_and_out_limit(message, compiler, source):
        with TemporaryCwd():
            upload_files()
            compile_fail({
                'source_file': source,
                'compiler': compiler,
                'out_file': '/out',
                'compilation_time_limit': time_limit,
                'compilation_real_time_limit': time_hard_limit,
                'compilation_result_size_limit': COMPILATION_RESULT_SIZE_LIMIT,
                'compilation_mem_limit': mem_limit * 2**10,
                'compilation_output_limit': COMPILATION_OUTPUT_LIMIT,
                }, message)

    @timed(time_hard_limit * 1.1)
    def _test_large_limit(message, compiler, source):
        with TemporaryCwd():
            upload_files()
            result_env = compile_fail({
                'source_file': source,
                'compiler': compiler,
                'out_file': '/out',
                'compilation_time_limit': time_limit,
                'compilation_real_time_limit': time_hard_limit,
                'compilation_output_limit': 100 * DEFAULT_COMPILER_OUTPUT_LIMIT
                }, message)

            ok_(len(result_env['compiler_output']) >
                    DEFAULT_COMPILER_OUTPUT_LIMIT)

    compilers = ['system-cpp']
    if ENABLE_SANDBOXED_COMPILERS:
        compilers += ['default-cpp']

    nasty_loopers = ['self-include.cpp',
                    'dev-random.cpp',
                    'infinite-warnings.cpp',
                    'templates-infinite-loop.cpp'
                    ]
    nasty_loopers = [ '/nasty-%s' % (s,) for s in nasty_loopers]

    exec_size_exceeders = [(250, '250MB-exec.cpp'), (5, '5MiB-exec.cpp')]
    exec_size_exceeders = [(s, '/nasty-%s' % f)
                           for s, f in exec_size_exceeders]

    for compiler in compilers:
        for size, fname in exec_size_exceeders:
            yield _test_size_and_out_limit, \
                'Compiled file size limit' if size < mem_limit else '', \
                compiler, fname

        for fname in nasty_loopers:
            yield _test_size_and_out_limit, None, compiler, fname

        yield _test_large_limit, None, compiler, '/nasty-infinite-warnings.cpp'

# TODO: Do not run slow tests by default
## Slow tests with real time/memory limit may behave differently (for example
## the compiler may run out of memory or generate 1GB of output etc.)
#@attr('slow')
#def test_compilation_error_gcc_slow():
#    test_compilation_error_gcc(DEFAULT_COMPILER_TIME_LIMIT,
#            DEFAULT_COMPILER_MEM_LIMIT)

def test_compilation_extremes():
    def _test(message, compiler, source):
        with TemporaryCwd():
            upload_files()
            compile_and_run({
                'source_file': source,
                'compiler': compiler,
                'out_file': '/out',
                'compilation_result_size_limit': COMPILATION_RESULT_SIZE_LIMIT,
                }, message)

    compilers = ['system-cpp']
    if ENABLE_SANDBOXED_COMPILERS:
        compilers += ['default-cpp']

    for compiler in compilers:
            yield _test, "0", compiler, '/extreme-4.9MB-static-exec.cpp'
