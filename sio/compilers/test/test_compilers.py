from __future__ import absolute_import
import glob
import os.path
import stat
import sys

import pytest
from sio.assertion_utils import ok_, eq_, timed

from sio.compilers.job import run
from sio.executors.common import run as run_from_executors
from sio.workers import ft
from filetracker.client.dummy import DummyClient
from sio.compilers.common import (
    DEFAULT_COMPILER_OUTPUT_LIMIT,
    DEFAULT_COMPILER_TIME_LIMIT,
    DEFAULT_COMPILER_MEM_LIMIT,
)
from sio.workers.executors import UnprotectedExecutor, PRootExecutor
from sio.workers.file_runners import get_file_runner
from sio.workers.util import TemporaryCwd, tempcwd

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
NO_JAVA_TESTS = os.environ.get('NO_JAVA_TESTS', False)


def in_(a, b, msg=None):
    """Shorthand for 'assert a in b, "%r not in %r" % (a, b)"""
    if a not in b:
        raise AssertionError(msg or "%r not in %r" % (a, b))


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
    if compiler_env.get('compiler', '').endswith('-java'):
        compiler_env['compilation_time_limit'] = 180000
    with TemporaryCwd('compile'):
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

    frunner = get_file_runner(executor, result_env)
    with frunner:
        renv = frunner(
            binary, program_args, stderr=sys.__stderr__, capture_output=True, **frkwargs
        )
    eq_(renv['return_code'], 0)
    eq_(renv['stdout'].decode().strip(), expected_output)

    os.remove(binary)


def _make_compilation_cases():
    compilers = ['system-']
    if ENABLE_SANDBOXED_COMPILERS:
        compilers += ['default-']

    for compiler in compilers:
        yield 'Hello World from c', compiler + 'c', '/simple.c', None
        yield '6.907167, 31.613478, 1.569796', compiler + 'c', '/libm.c', ['999.412']
        yield 'Hello World from cpp', compiler + 'cpp', '/simple.cpp', None
        yield 'Hello World from cc', compiler + 'cc', '/simple.cc', None
        yield '3\n5\n5\n7\n9\n10', compiler + 'cpp', '/libstdc++.cpp', None
        yield 'Hello World from pas', compiler + 'pas', '/simple.pas', None
        if not NO_JAVA_TESTS:
            yield 'Hello World from java', compiler + 'java', '/simple.java', None
        # Note that "output-only" compiler is tested in test_output_compilation_and_running

    if ENABLE_SANDBOXED_COMPILERS:
        yield '12903', 'default-cpp', '/cpp11.cpp', None
        yield 'Hello World from GNU99', 'default-c', '/gnu99.c', None


@pytest.mark.parametrize(
    "message,compiler,source,program_args",
    [test_case for test_case in _make_compilation_cases()],
)
def test_compilation(message, compiler, source, program_args):
    with TemporaryCwd():
        upload_files()
        compile_and_run(
            {
                'source_file': source,
                'compiler': compiler,
                'out_file': '/out',
            },
            message,
            program_args,
        )


@pytest.mark.parametrize("source", [('/simple.txt')])
def test_output_compilation_and_running(source):
    with TemporaryCwd():
        upload_files()
        result_env = run(
            {
                'source_file': source,
                'compiler': 'output-only',
            }
        )
        eq_(result_env['result_code'], 'OK')
        eq_(result_env['exec_info'], {'mode': 'output-only'})

        ft.download(result_env, 'out_file', tempcwd('out.txt'))
        ft.download({'source_file': source}, 'source_file', tempcwd('source.txt'))
        with open(tempcwd('out.txt'), 'r') as outfile:
            with open(tempcwd('source.txt'), 'r') as sourcefile:
                eq_(outfile.read(), sourcefile.read())

        post_run_env = run_from_executors(
            {
                'exec_info': result_env['exec_info'],
                'exe_file': result_env['out_file'],
                'check_output': True,
                'hint_file': source,
            },
            executor=None,
        )
        eq_(post_run_env['result_code'], 'OK')

        ft.download(post_run_env, 'out_file', tempcwd('out.txt'))
        ft.download({'source_file': source}, 'source_file', tempcwd('source.txt'))
        with open(tempcwd('out.txt'), 'r') as outfile:
            with open(tempcwd('source.txt'), 'r') as sourcefile:
                eq_(outfile.read(), sourcefile.read())


def _make_compilation_with_additional_library_cases():
    compilers = ['system-']
    if ENABLE_SANDBOXED_COMPILERS:
        compilers += ['default-']

    for compiler in compilers:
        yield 'Hello World from c-lib', compiler + 'c', '/simple-lib.c', '/library.c', '/library.h'
        yield 'Hello World from cpp-lib', compiler + 'cpp', '/simple-lib.cpp', '/library.cpp', '/library.h'
        yield 'Hello World from pas-lib', compiler + 'pas', '/simple-lib.pas', '/pas_library.pas', {}
        if not NO_JAVA_TESTS:
            yield 'Hello World from java-lib', compiler + 'java', '/simple_lib.java', '/library.java', {}


@pytest.mark.parametrize(
    "message,compiler,source,sources,includes",
    [test_case for test_case in _make_compilation_with_additional_library_cases()],
)
def test_compilation_with_additional_library(
    message, compiler, source, sources, includes
):
    with TemporaryCwd():
        upload_files()

        compile_and_run(
            {
                'source_file': source,
                'additional_includes': includes,
                'additional_sources': sources,
                'compiler': compiler,
                'out_file': '/out',
            },
            message,
        )


def _make_compilation_with_additional_library_and_directory_params_cases():
    compilers = ['system-']
    if ENABLE_SANDBOXED_COMPILERS:
        compilers += ['default-']

    for compiler in compilers:
        yield 'Hello World from c-lib', compiler + 'c', '/simple-lib.c'
        yield 'Hello World from cpp-lib', compiler + 'cpp', '/simple-lib.cpp'
        yield 'Hello World from pas-lib', compiler + 'pas', '/simple-lib.pas'
        if not NO_JAVA_TESTS:
            yield 'Hello World from java-lib', compiler + 'java', '/simple_lib.java'


@pytest.mark.parametrize(
    "message,compiler,source",
    [
        test_case
        for test_case in _make_compilation_with_additional_library_and_directory_params_cases()
    ],
)
def test_compilation_with_additional_library_and_dictionary_params(
    message, compiler, source
):
    with TemporaryCwd():
        upload_files()

        compile_and_run(
            {
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
            },
            message,
        )


def _make_compilation_with_additional_archive_cases():
    yield 'Hello World from c-lib', 'system-c', '/simple-lib.c', '/library.c', '/library-archive.zip', [
        '../b.txt'
    ]

    if ENABLE_SANDBOXED_COMPILERS:
        yield 'Hello World from c-lib', 'default-c', '/simple-lib.c', '/library.c', '/library-archive.zip', [
            '../b.txt'
        ]


@pytest.mark.parametrize(
    "message,compiler,source,sources,archive,unexpected_files",
    [test_case for test_case in _make_compilation_with_additional_archive_cases()],
)
def test_compilation_with_additional_archive(
    message, compiler, source, sources, archive, unexpected_files
):
    with TemporaryCwd(inner_directory='one_more_level'):
        upload_files()

        compile_and_run(
            {
                'source_file': source,
                'additional_sources': sources,
                'additional_archive': archive,
                'compiler': compiler,
                'out_file': '/out',
            },
            message,
        )

        for f in unexpected_files:
            ok_(not os.path.exists(f))


COMPILATION_OUTPUT_LIMIT = 100  # in bytes
COMPILATION_RESULT_SIZE_LIMIT = 5 * 1024 * 1024  # in bytes


def compile_fail(compiler_env, expected_in_compiler_output=None):
    """Helper function for compiling and asserting that it fails."""

    result_env = run(compiler_env)
    print_env(result_env)

    eq_(result_env['result_code'], 'CE')

    if 'compilation_output_limit' not in compiler_env:
        ok_(len(result_env['compiler_output']) <= DEFAULT_COMPILER_OUTPUT_LIMIT)
    elif compiler_env['compilation_output_limit'] is not None:
        ok_(
            len(result_env['compiler_output'])
            <= compiler_env['compilation_output_limit']
        )

    if expected_in_compiler_output:
        in_(expected_in_compiler_output, result_env['compiler_output'])

    return result_env


# Test with overly-limited resources
def _get_limits():
    mem_limit = 128
    time_limit = 2000
    time_hard_limit = 3 * time_limit
    return {
        'mem_limit': mem_limit,
        'time_limit': time_limit,
        'time_hard_limit': time_hard_limit,
    }


def _make_compilation_error_gcc_size_and_out_limit_cases():
    mem_limit = _get_limits()['mem_limit']
    compilers = ['system-cpp']
    if ENABLE_SANDBOXED_COMPILERS:
        compilers += ['default-cpp']

    nasty_loopers = [
        'self-include.cpp',
        'dev-random.cpp',
        'infinite-warnings.cpp',
        'templates-infinite-loop.cpp',
    ]
    nasty_loopers = ['/nasty-%s' % (s,) for s in nasty_loopers]

    exec_size_exceeders = [(250, '250MB-exec.cpp'), (5, '5MiB-exec.cpp')]
    exec_size_exceeders = [(s, '/nasty-%s' % f) for s, f in exec_size_exceeders]

    for compiler in compilers:
        for size, fname in exec_size_exceeders:
            yield 'Compiled file size limit' if size < mem_limit else '', compiler, fname

        for fname in nasty_loopers:
            yield None, compiler, fname


@pytest.mark.parametrize(
    "message,compiler,source",
    [test_case for test_case in _make_compilation_error_gcc_size_and_out_limit_cases()],
)
@timed(_get_limits()['time_hard_limit'] * 1.1)
def test_compilation_error_gcc_size_and_out_limit(message, compiler, source):
    mem_limit = _get_limits()['mem_limit']
    time_limit = _get_limits()['time_limit']
    time_hard_limit = _get_limits()['time_hard_limit']
    with TemporaryCwd():
        upload_files()
        compile_fail(
            {
                'source_file': source,
                'compiler': compiler,
                'out_file': '/out',
                'compilation_time_limit': time_limit,
                'compilation_real_time_limit': time_hard_limit,
                'compilation_result_size_limit': COMPILATION_RESULT_SIZE_LIMIT,
                'compilation_mem_limit': mem_limit * 2 ** 10,
                'compilation_output_limit': COMPILATION_OUTPUT_LIMIT,
            },
            message,
        )


def _make_compilation_error_gcc_large_limit_cases():
    compilers = ['system-cpp']
    if ENABLE_SANDBOXED_COMPILERS:
        compilers += ['default-cpp']

    for compiler in compilers:
        yield None, compiler, '/nasty-infinite-warnings.cpp'


@pytest.mark.parametrize(
    "message,compiler,source",
    [test_case for test_case in _make_compilation_error_gcc_large_limit_cases()],
)
@timed(_get_limits()['time_hard_limit'] * 1.1)
def test_compilation_error_gcc_large_limit(message, compiler, source):
    time_limit = _get_limits()['time_limit']
    time_hard_limit = _get_limits()['time_hard_limit']
    with TemporaryCwd():
        upload_files()
        result_env = compile_fail(
            {
                'source_file': source,
                'compiler': compiler,
                'out_file': '/out',
                'compilation_time_limit': time_limit,
                'compilation_real_time_limit': time_hard_limit,
                'compilation_output_limit': 100 * DEFAULT_COMPILER_OUTPUT_LIMIT,
            },
            message,
        )

        ok_(len(result_env['compiler_output']) > DEFAULT_COMPILER_OUTPUT_LIMIT)


# TODO: Do not run slow tests by default
## Slow tests with real time/memory limit may behave differently (for example
## the compiler may run out of memory or generate 1GB of output etc.)
# @attr('slow')
# def test_compilation_error_gcc_slow():
#    test_compilation_error_gcc(DEFAULT_COMPILER_TIME_LIMIT,
#            DEFAULT_COMPILER_MEM_LIMIT)


def _make_compilation_extremes_cases():
    compilers = ['system-cpp']
    if ENABLE_SANDBOXED_COMPILERS:
        compilers += ['default-cpp']

    for compiler in compilers:
        yield "0", compiler, '/extreme-4.9MB-static-exec.cpp'


@pytest.mark.parametrize(
    "message,compiler,source",
    [test_case for test_case in _make_compilation_extremes_cases()],
)
def test_compilation_extremes(message, compiler, source):
    with TemporaryCwd():
        upload_files()
        compile_and_run(
            {
                'source_file': source,
                'compiler': compiler,
                'out_file': '/out',
                'compilation_result_size_limit': COMPILATION_RESULT_SIZE_LIMIT,
            },
            message,
        )
