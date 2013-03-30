from nose.tools import ok_, eq_, timed

from sio.compilers.job import run
from sio.workers import ft
from sio.workers.execute import execute
from filetracker.dummy import DummyClient
from sio.compilers.common import DEFAULT_COMPILER_OUTPUT_LIMIT, \
        DEFAULT_COMPILER_TIME_LIMIT

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
#    can enable them by setting environment variable TEST_SANDBOXES to 1.
#    All needed dependencies will be downloaded automagically
#    by sio.workers.sandbox.
#

SOURCES = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sources')
ENABLE_SANDBOXED_COMPILERS = os.environ.get('TEST_SANDBOXES',
                                            False)

def in_(a, b, msg=None):
    """Shorthand for 'assert a in b, "%r not in %r" % (a, b)"""
    if a not in b:
        raise AssertionError(msg or "%r not in %r" % (a, b))


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

    # Dummy sandbox doesn't support asking for versioned filename
    out_file = compiler_env['out_file']
    result_env = run(compiler_env)

    eq_(result_env['result_code'], 'OK')
    binary = ft.download({'path': out_file}, 'path')

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

    compilers = ['system-']
    if ENABLE_SANDBOXED_COMPILERS:
        compilers += ['default-']

    for compiler in compilers:
        yield _test, 'Hello World from c', compiler + 'c', '/simple.c'
        yield _test, '6.907167, 31.613478, 1.569796', compiler + 'c', '/libm.c'
        yield _test, 'Hello World from cpp', compiler + 'cpp', '/simple.cpp'
        yield _test, '3\n5\n5\n7\n9\n10', compiler + 'cpp', '/libstdc++.cpp'
        yield _test, 'Hello World from pas', compiler + 'pas', '/simple.pas'

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

    yield _test, 'Hello World from c-lib', 'system-c', '/simple-lib.c', \
          '/library.c', '/library.h'
    yield _test, 'Hello World from cpp-lib', 'system-cpp', '/simple-lib.cpp', \
          '/library.cpp', '/library.h'
    yield _test, 'Hello World from pas-lib', 'system-pas', '/simple-lib.pas', \
          '/pas_library.pas'

    if ENABLE_SANDBOXED_COMPILERS:
        yield _test, 'Hello World from c-lib', 'default-c', \
              '/simple-lib.c', '/library.c', '/library.h'
        yield _test, 'Hello World from cpp-lib', 'default-cpp', \
              '/simple-lib.cpp', '/library.cpp', '/library.h'
        yield _test, 'Hello World from pas-lib', 'default-pas', \
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
        yield _test, 'Hello World from c-lib', 'default-c', \
              '/simple-lib.c'
        yield _test, 'Hello World from cpp-lib', 'default-cpp', \
              '/simple-lib.cpp'
        yield _test, 'Hello World from pas-lib', 'default-pas', \
              '/simple-lib.pas'

COMPILATION_TIME_HARD_LIMIT = 2 + 3 * DEFAULT_COMPILER_TIME_LIMIT
COMPILATION_OUTPUT_LIMIT = 100
COMPILATION_RESULT_SIZE_LIMIT = 5 * 1024 * 1024

def compile_fail(compiler_env, expected_in_compiler_output=None):
    """Helper function for compiling and asserting that it fails."""

    result_env = run(compiler_env)

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

def test_compilation_error_gcc():
    @timed(COMPILATION_TIME_HARD_LIMIT)
    def _test_size_and_out_limit(message, compiler, source):
        with TemporaryCwd():
            upload_files()
            compile_fail({
                'source_file': source,
                'compiler': compiler,
                'out_file': '/out',
                'compilation_result_size_limit': COMPILATION_RESULT_SIZE_LIMIT,
                'compilation_mem_limit': 512 << 10,
                'compilation_output_limit': COMPILATION_OUTPUT_LIMIT,
                }, message)

    @timed(COMPILATION_TIME_HARD_LIMIT)
    def _test_large_limit(message, compiler, source):
        with TemporaryCwd():
            upload_files()
            result_env = compile_fail({
                'source_file': source,
                'compiler': compiler,
                'out_file': '/out',
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

    exec_size_exceeders = ['250MB-exec.cpp', '5MiB-exec.cpp']
    exec_size_exceeders = [ '/nasty-%s' % (s,) for s in exec_size_exceeders]

    for compiler in compilers:
        for fname in exec_size_exceeders:
            yield _test_size_and_out_limit, \
                'Compiled file size limit exceeded', compiler, fname

        for fname in nasty_loopers:
            yield _test_size_and_out_limit, None, compiler, fname

        yield _test_large_limit, None, compiler, '/nasty-infinite-warnings.cpp'

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
