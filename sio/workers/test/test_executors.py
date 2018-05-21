import glob
import os.path
import re
import filecmp

from nose.tools import ok_, eq_, assert_not_equal, nottest, raises, \
        assert_raises
from filetracker.client.dummy import DummyClient

from sio.compilers.job import run as run_compiler
from sio.executors.common import run as run_executor
from sio.executors.ingen import run as run_ingen
from sio.executors.inwer import run as run_inwer
from sio.executors.checker import RESULT_STRING_LENGTH_LIMIT
from sio.workers import ft
from sio.workers.execute import execute
from sio.workers.executors import UnprotectedExecutor, \
        DetailedUnprotectedExecutor, SupervisedExecutor, VCPUExecutor, \
        ExecError, _SIOSupervisedExecutor
from sio.workers.file_runners import get_file_runner
from sio.workers.util import tempcwd, TemporaryCwd

# sio2-executors tests
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
# 2) By default, executors are excluded from the
#    testing, due to their rather unwieldy dependencies. You
#    can enable them by setting environment variable TEST_SANDBOXES to 1.
#    All needed dependencies will be downloaded automagically
#    by sio.workers.sandbox.
#

SOURCES = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sources')
ENABLE_SANDBOXES = os.environ.get('TEST_SANDBOXES', False)
NO_JAVA_TESTS = os.environ.get('NO_JAVA_TESTS', False)

def in_(a, b, msg=None):
    """Shorthand for 'assert a in b, "%r not in %r" % (a, b)"""
    if a not in b:
        raise AssertionError(msg or "%r not in %r" % (a, b))

def not_in_(a, b, msg=None):
    """Shorthand for 'assert a not in b, "%r not in %r" % (a, b)"""
    if a in b:
        raise AssertionError(msg or "%r not in %r" % (a, b))


def upload_files():
    """Uploads all files from SOURCES to a newly created dummy filetracker"""

    # DummyClient operates in the working directory.
    ft.set_instance(DummyClient())
    for path in glob.glob(os.path.join(SOURCES, '*')):
        ft.upload({'path': '/' + os.path.basename(path)}, 'path', path)

def compile(source, output='/exe', use_sandboxes=ENABLE_SANDBOXES):
    ext = os.path.splitext(source.split('@')[0])[1][1:]
    compiler_env = {
        'source_file': source,
        'compiler': (use_sandboxes and 'default-' or 'system-') + ext,
        'out_file': output,
        'compilation_time_limit': 180000,
    }

    # Dummy sandbox doesn't support asking for versioned filename
    out_file = compiler_env['out_file']
    result_env = run_compiler(compiler_env)
    result_env['out_file'] = out_file
    print_env(result_env)

    eq_(result_env['result_code'], 'OK')
    return result_env

def compile_and_execute(source, executor, **exec_args):
    cenv = compile(source,
                   use_sandboxes=isinstance(executor, _SIOSupervisedExecutor))
    frunner = get_file_runner(executor, cenv)

    ft.download({'exe_file': cenv['out_file']}, 'exe_file',
                frunner.preferred_filename())
    os.chmod(tempcwd('exe'), 0700)
    ft.download({'in_file': '/input'}, 'in_file', 'in')

    with frunner:
        with open(tempcwd('in'), 'rb') as inf:
            renv = frunner(tempcwd('exe'), [], stdin=inf, **exec_args)

    return renv

def compile_and_run(source, executor_env, executor, use_sandboxes=False):
    renv = compile(source,
                   use_sandboxes=isinstance(executor, _SIOSupervisedExecutor))
    executor_env['exe_file'] = renv['out_file']
    executor_env['exec_info'] = renv['exec_info']
    return run_executor(executor_env, executor, use_sandboxes=use_sandboxes)

def print_env(env):
    from pprint import pprint
    pprint(env)

def fail(*args, **kwargs):
    ok_(False, "Forced fail")

MEMORY_CHECKS = ['30MiB-bss.c', '30MiB-data.c', '30MiB-malloc.c',
        '30MiB-stack.c']
JAVA_MEMORY_CHECKS = ['mem30MiBheap.java', 'mem30MiBstack.java']
MEMORY_CHECKS_LIMIT = 30 * 1024  # in KiB
SMALL_OUTPUT_LIMIT = 50  # in B
CHECKING_EXECUTORS = [DetailedUnprotectedExecutor]
SANDBOXED_CHECKING_EXECUTORS = [SupervisedExecutor, VCPUExecutor]

# Status helpers
def res_ok(env):
    eq_('OK', env['result_code'])

def res_not_ok(env):
    assert_not_equal(env['result_code'], 'OK')

def res_wa(env):
    eq_('WA', env['result_code'])

def res_re(reason):
    def inner(env):
        eq_('RE', env['result_code'])
        in_(str(reason), env['result_string'])
    return inner

def res_tle(env):
    eq_(env['result_code'], 'TLE')

def res_rv(msg):
    def inner(env):
        eq_('RV', env['result_code'])
        in_(msg, env['result_string'])
    return inner

def due_signal(code):
    def inner(env):
        res_re('due to signal')(env)
        in_(str(code), env['result_string'])
    return inner

# High-level tests
def test_running():
    def _test(source, executor, callback):
        with TemporaryCwd():
            upload_files()
            result_env = compile_and_run(source, {
                'in_file': '/input',
                'exec_time_limit': 1000
            }, executor)
            print_env(result_env)
            callback(result_env)

    executors = CHECKING_EXECUTORS
    if ENABLE_SANDBOXES:
        executors = executors + SANDBOXED_CHECKING_EXECUTORS

    for executor in executors:
        yield _test, '/add_print.c', executor(), res_ok

        if executor != VCPUExecutor and not NO_JAVA_TESTS:
            yield _test, '/add_print.java', executor(), res_ok

def test_zip():
    with TemporaryCwd():
        upload_files()
        compile_and_run("/echo.c", {
            'in_file': '/input.zip',
            'out_file': '/output',
            'exec_mem_limit': 102400
            }, DetailedUnprotectedExecutor())
        ft.download({'in_file': '/input'}, 'in_file', 'out.expected')
        ft.download({'out_file': '/output'}, 'out_file', 'out.real')
        ok_(filecmp.cmp(tempcwd('out.expected'),
                        tempcwd('out.real')))

def test_common_memory_limiting():
    def _test(source, mem_limit, executor, callback):
        with TemporaryCwd():
            upload_files()
            result_env = compile_and_run(source, {
                'in_file': '/input',
                'exec_mem_limit': mem_limit
                }, executor)
            print_env(result_env)
            callback(result_env)

    def res_mle_or_fail(env):
        res_not_ok(env)
        if env['result_code'] != 'MLE':
            due_signal(11)(env)  # sigsegv

    for test in MEMORY_CHECKS:
        for executor in CHECKING_EXECUTORS:
            yield _test, "/" + test, int(MEMORY_CHECKS_LIMIT*1.2),\
                executor(), res_ok
            yield _test, "/" + test, int(MEMORY_CHECKS_LIMIT*0.9), \
                executor(), res_not_ok

        if ENABLE_SANDBOXES:
            for executor in SANDBOXED_CHECKING_EXECUTORS:
                yield _test, "/" + test, int(MEMORY_CHECKS_LIMIT*1.2), \
                        executor(),  res_ok
                yield _test, "/" + test, int(MEMORY_CHECKS_LIMIT*0.9), \
                        executor(), res_mle_or_fail

    if not NO_JAVA_TESTS:
        for test in JAVA_MEMORY_CHECKS:
            for executor in CHECKING_EXECUTORS:
                # XXX: The OpenJDK JVM has enormous stack memory overhead!
                oh = 2.5 if 'stack' in test else 1.2

                yield _test, "/" + test, int(MEMORY_CHECKS_LIMIT*oh), \
                    executor(), res_ok
                yield _test, "/" + test, int(MEMORY_CHECKS_LIMIT*0.9), \
                    executor(), res_not_ok

            if ENABLE_SANDBOXES:
                executor = SupervisedExecutor
                yield _test, "/" + test, int(MEMORY_CHECKS_LIMIT*1.2), \
                    executor(), res_ok
                yield _test, "/" + test, int(MEMORY_CHECKS_LIMIT*0.8), \
                    executor(), res_not_ok

def test_common_time_limiting():
    def _test(source, time_limit, executor, callback):
        with TemporaryCwd():
            upload_files()
            result_env = compile_and_run(source, {
                'in_file': '/input',
                'exec_time_limit': time_limit
            }, executor)
            print_env(result_env)
            callback(result_env)

    for executor in CHECKING_EXECUTORS:
        yield _test, '/procspam.c', 500, executor(), res_tle
        if not NO_JAVA_TESTS:
            yield _test, '/procspam.java', 500, executor(), res_tle

    if ENABLE_SANDBOXES:
        for executor in SANDBOXED_CHECKING_EXECUTORS:
            yield _test, "/procspam.c", 200, executor(), res_tle
            yield _test, "/1-sec-prog.c", 10, executor(), res_tle

        yield _test, "/1-sec-prog.c", 1000, SupervisedExecutor(), res_ok
        yield _test, "/1-sec-prog.c", 990, VCPUExecutor(), res_tle
        yield _test, "/1-sec-prog.c", 1100, VCPUExecutor(), res_ok
        if not NO_JAVA_TESTS:
            yield _test, "/proc1secprog.java", 100, SupervisedExecutor(), \
                    res_tle
            yield _test, "/proc1secprog.java", 1000, SupervisedExecutor(), \
                    res_ok

def test_outputting_non_utf8():
    if ENABLE_SANDBOXES:
        with TemporaryCwd():
            upload_files()
            renv = compile_and_run('/output-non-utf8.c', {
                    'in_file': '/input',
                    'check_output': True,
                    'hint_file': '/input',
                    }, SupervisedExecutor(), use_sandboxes=True)
            print_env(renv)
            in_('42', renv['result_string'])
            ok_(renv['result_string'].decode('utf8'))

def test_truncating_output():
    with TemporaryCwd():
        upload_files()
        checker_bin = compile('/chk-output-too-long.c',
                '/chk-output-too-long.e')['out_file']
    with TemporaryCwd():
        renv = compile_and_run('/output-too-long.c', {
                'in_file': '/input',
                'check_output': True,
                'hint_file': '/input',
                'chk_file': checker_bin,
                }, DetailedUnprotectedExecutor(), use_sandboxes=False)
        length = len(renv['result_string'])
        if length > RESULT_STRING_LENGTH_LIMIT:
            raise AssertionError("result_string too long, %d > %d"
                    % (length, RESULT_STRING_LENGTH_LIMIT))

def test_untrusted_checkers():
    def _test(checker, callback, sandboxed=True):
        with TemporaryCwd():
            upload_files()
            checker_bin = compile(checker, '/chk.e')['out_file']
        with TemporaryCwd():
            executor = SupervisedExecutor(use_program_return_code=True) if \
                    sandboxed else DetailedUnprotectedExecutor()
            renv = compile_and_run('/add_print.c', {
                    'in_file': '/input',
                    'check_output': True,
                    'hint_file': '/hint',
                    'chk_file': checker_bin,
                    'untrusted_checker': True,
            }, executor, use_sandboxes=sandboxed)
            print_env(renv)
            if callback:
                callback(renv)

    def ok_42(env):
        res_ok(env)
        eq_(42, int(env['result_percentage']))

    # Test if unprotected execution allows for return code 1
    yield _test, '/chk-rtn1.c', None, False
    # Test if unprotected execution allows for return code 2
    yield raises(SystemError)(_test), '/chk-rtn2.c', None, False

    if ENABLE_SANDBOXES:
        yield _test, '/chk.c', ok_42
        # Broken checker
        yield _test, '/open2.c', res_wa
        # Wrong model solution
        yield raises(SystemError)(_test), '/chk-rtn2.c', None

def test_inwer():
    def _test(inwer, in_file, use_sandboxes, callback):
        with TemporaryCwd():
            upload_files()
            inwer_bin = compile(inwer, '/inwer.e')['out_file']
        with TemporaryCwd():
            env = {
                    'in_file': in_file,
                    'exe_file': inwer_bin,
                    'use_sandboxes': use_sandboxes,
                    'inwer_output_limit': SMALL_OUTPUT_LIMIT,
                    }
            renv = run_inwer(env)
            print_env(renv)
            if callback:
                callback(renv)

    def check_inwer_ok(env):
        eq_(env['result_code'], "OK")
        ok_(env['stdout'][0].startswith("OK"))

    def check_inwer_wrong(env):
        assert_not_equal(env['result_code'], "OK")
        in_("WRONG", env['stdout'][0])

    def check_inwer_faulty(env):
        eq_(env['result_code'], "OK")
        ok_(not env['stdout'][0].startswith("OK"))

    def check_inwer_big_output(use_sandboxes):
        def inner(env):
            if(use_sandboxes):
                eq_(env['result_code'], "OLE")
            else:
                eq_(env['result_code'], "OK")
                eq_(env['stdout'], ['A' * SMALL_OUTPUT_LIMIT])
        return inner

    sandbox_options = [False]
    if ENABLE_SANDBOXES:
        sandbox_options.append(True)

    for use_sandboxes in sandbox_options:
        yield _test, '/inwer.c', '/inwer_ok', use_sandboxes, check_inwer_ok
        yield _test, '/inwer.c', '/inwer_wrong', use_sandboxes, \
                check_inwer_wrong
        yield _test, '/inwer_faulty.c', '/inwer_ok', use_sandboxes, \
                check_inwer_faulty
        yield _test, '/inwer_big_output.c', '/inwer_ok', use_sandboxes, \
                check_inwer_big_output(use_sandboxes)

def test_ingen():
    def _test(ingen, re_string, upload_dir, use_sandboxes, callback):
        with TemporaryCwd():
            upload_files()
            ingen_bin = compile(ingen, '/ingen.e')['out_file']
        with TemporaryCwd():
            env = {
                    're_string': re_string,
                    'collected_files_path': '/' + upload_dir,
                    'exe_file': ingen_bin,
                    'use_sandboxes': use_sandboxes,
                    'ingen_output_limit': SMALL_OUTPUT_LIMIT,
                    }
            renv = run_ingen(env)
            print_env(renv)
            if callback:
                callback(renv)

    def check_upload(upload_dir, expected_files, expected_output):
        def inner(env):
            eq_(env['return_code'], 0)
            eq_(env['stdout'], expected_output)
            collected = env['collected_files']
            eq_(len(expected_files), len(collected))
            for filename, path in collected.iteritems():
                in_(filename, expected_files)
                unversioned_path = '/%s/%s' % (upload_dir, filename)
                upload_re_str = '%s@\d+' % (unversioned_path)
                upload_re = re.compile(upload_re_str)
                ok_(upload_re.match(path), 'Unexpected filetracker path')

                ft.download({'in': unversioned_path}, 'in', filename)
                eq_(expected_files[filename], open(tempcwd(filename)).read())
        return inner

    def check_proot_fail(env):
        eq_(env['return_code'], 139)

    sandbox_options = [False]
    if ENABLE_SANDBOXES:
        sandbox_options.append(True)

    test_sets = [
            {
                'program': '/ingen.c',
                'dir': 'somedir',
                're_string': r'.*\.upload',
                'files': {
                    'two.upload': '2\n',
                    'five.five.upload': '5\n',
                    },
                'output': ["Everything OK", "Really"],
                },
            {
                'program': '/ingen_big_output.c',
                'dir': 'other_dir',
                're_string': r'.*_upload',
                'files': {
                    'three_upload': '3\n',
                    },
                'output': ['A' * SMALL_OUTPUT_LIMIT],
                },
            ]

    for use_sandboxes in sandbox_options:
        for test in test_sets:
            yield _test, test['program'], test['re_string'], test['dir'], \
                    use_sandboxes, \
                    check_upload(test['dir'], test['files'], test['output'])
    if ENABLE_SANDBOXES:
        yield _test, '/ingen_nosy.c', 'myfile.txt', 'somedir', True, \
                check_proot_fail

# Direct tests
def test_uploading_out():
    with TemporaryCwd():
        upload_files()
        renv = compile_and_run('/add_print.c', {
            'in_file': '/input',
            'out_file': '/output',
            'upload_out': True,
        }, DetailedUnprotectedExecutor())
        print_env(renv)

        ft.download({'path': '/output'}, 'path', 'd_out')
        in_('84', open(tempcwd('d_out')).read())

@nottest
def _test_transparent_exec(source, executor, callback, kwargs):
    with TemporaryCwd():
        upload_files()
        ft.download({'path': '/somefile'}, 'path', tempcwd('somefile'))
        result_env = compile_and_execute(source, executor, **kwargs)
        print_env(result_env)
        if callback:
            callback(result_env)
@nottest
def _test_exec(source, executor, callback, kwargs):
    kwargs.setdefault('ignore_errors', True)
    _test_transparent_exec(source, executor, callback, kwargs)

@nottest
def _test_raw(cmd, executor, callback, kwargs):
    with TemporaryCwd():
        with executor:
            result_env = executor(cmd, **kwargs)
        print_env(result_env)
        callback(result_env)

def test_capturing_stdout():
    def only_stdout(env):
        in_('stdout', env['stdout'])
        not_in_('stderr', env['stdout'])

    def with_stderr(env):
        in_('stdout', env['stdout'])
        in_('stderr', env['stdout'])

    def lines_split(env):
        ok_(isinstance(env['stdout'], list))
        eq_(len(env['stdout']), 3)

    executors = [UnprotectedExecutor]
    if ENABLE_SANDBOXES:
        executors = executors + [VCPUExecutor]

    for executor in executors:
        yield _test_exec, '/add_print.c', executor(), only_stdout, \
                {'capture_output': True}
        yield _test_exec, '/add_print.c', executor(), lines_split, \
                {'capture_output': True, 'split_lines': True}
        yield _test_exec, '/add_print.c', executor(), with_stderr, \
                {'capture_output': True, 'forward_stderr': True}


def test_return_codes():
    def ret_42(env):
        eq_(42, env['return_code'])

    executors = [UnprotectedExecutor]

    for executor in executors:
        yield raises(ExecError)(_test_transparent_exec), '/return-scanf.c',\
                executor(), None, {}
        yield _test_transparent_exec, '/return-scanf.c', executor(), ret_42, \
                {'ignore_errors': True}
        yield _test_transparent_exec, '/return-scanf.c', executor(), ret_42, \
                {'extra_ignore_errors': (42,)}

    checking_executors = CHECKING_EXECUTORS
    if ENABLE_SANDBOXES:
        checking_executors = checking_executors + SANDBOXED_CHECKING_EXECUTORS

    for executor in checking_executors:
        yield _test_exec, '/return-scanf.c', executor(), res_re(42), {}

    if ENABLE_SANDBOXES:
        yield _test_exec, '/return-scanf.c', SupervisedExecutor(), res_ok, \
                {'ignore_return': True}

def test_output_limit():
    def ole(env):
        eq_('OLE', env['result_code'])

    def stdout_shorter(limit):
        def inner(env):
            ok_(len(env['stdout']) <= limit)
        return inner

    executors = [UnprotectedExecutor]

    for executor in executors:
        yield _test_exec, '/add_print.c', executor(), stdout_shorter(10), \
                {'capture_output': True, 'output_limit': 10}

    checking_executors = [] # UnprotectedExecutor doesn't support OLE
    if ENABLE_SANDBOXES:
        checking_executors = checking_executors + SANDBOXED_CHECKING_EXECUTORS

    for executor in checking_executors:
        yield _test_exec, '/add_print.c', executor(), ole, \
            {'output_limit': 10}
        yield _test_exec, '/iospam-hard.c', executor(), ole, {} # Default

def test_signals():
    checking_executors = CHECKING_EXECUTORS
    if ENABLE_SANDBOXES:
        checking_executors = checking_executors + SANDBOXED_CHECKING_EXECUTORS

    SIGNALS_CHECKS = [
            ('sigabrt.c', 6),
            ('sigfpe.c', 8),
            ('sigsegv.c', 11),
            ]

    for executor in checking_executors:
        for (prog, code) in SIGNALS_CHECKS:
            yield _test_exec, '/' + prog, executor(), due_signal(code), {}

def test_rule_violation():
    checking_executors = []
    if ENABLE_SANDBOXES:
        checking_executors = checking_executors + SANDBOXED_CHECKING_EXECUTORS

    for executor in checking_executors:
        yield _test_exec, '/open.c', executor(), res_rv('opening files'), {}

def test_local_opens():
    def change(env):
        res_ok(env)
        eq_('13', open(tempcwd('somefile')).read().strip())
        ok_(os.path.exists(tempcwd('./not_existing')))

    def nochange(env):
        res_re(1)(env)
        eq_('42', open(tempcwd('somefile')).read().strip())
        ok_(not os.path.exists(tempcwd('./not_existing')))

    # Test that this is in fact unsafe
    yield _test_exec, '/openrw.c', DetailedUnprotectedExecutor(), change, {}

    if ENABLE_SANDBOXES:
        yield _test_exec, '/open.c', SupervisedExecutor(), \
                res_rv('opening files'), {}
        yield _test_exec, '/openrw.c', SupervisedExecutor(), \
                res_rv('opening files'), {}
        yield _test_exec, '/open.c', \
                SupervisedExecutor(allow_local_open=True), res_ok, {}
        yield _test_exec, '/openrw.c', \
                SupervisedExecutor(allow_local_open=True), nochange, {}
        yield _test_exec, '/open2.c', \
                SupervisedExecutor(allow_local_open=True), res_re(1), {}

def test_vcpu_accuracy():
    def used_1sec(env):
        eq_('OK', env['result_code'])
        eq_(1000, env['time_used'])

    if ENABLE_SANDBOXES:
        yield _test_exec, '/1-sec-prog.c', VCPUExecutor(), used_1sec, {}

def test_real_time_limit():
    def real_tle(limit):
        def inner(env):
            eq_('TLE', env['result_code'])
            ok_(env['real_time_used'] > limit)
        return inner

    def syscall_limit(env):
        eq_('TLE', env['result_code'])
        in_('syscalls', env['result_string'])

    checking_executors = CHECKING_EXECUTORS
    if ENABLE_SANDBOXES:
        # FIXME: Supervised ignores realtime
        checking_executors = checking_executors + [VCPUExecutor]

    for executor in checking_executors:
        yield _test_exec, '/procspam.c', executor(), real_tle, \
            {'real_time_limit': 1000, 'time_limit': 10000}

    for executor in CHECKING_EXECUTORS:
        yield _test_exec, '/iospam.c', executor(), real_tle, \
            {'real_time_limit': 1000, 'time_limit': 10000}

    if ENABLE_SANDBOXES:
        yield _test_exec, '/iospam.c', VCPUExecutor(), syscall_limit, \
            {'time_limit': 500}

# Raw executing
def test_execute():
    with TemporaryCwd():
        rc, out = execute(['echo', '2'])
        eq_(rc, 0)
        eq_(out, '2\n')
        rc, out = execute(['exit', '1'], ignore_errors=True)
        eq_(rc, 1)

        assert_raises(ExecError, execute, ['exit', '1'])

        rc, out = execute(['mkdir', tempcwd('spam')])
        eq_(rc, 0)
        rc, out = execute(['ls', tempcwd()])
        in_('spam', out)

