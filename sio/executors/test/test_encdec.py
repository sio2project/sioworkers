import glob
import os.path

from filetracker.client.dummy import DummyClient
from sio.assertion_utils import ok_, eq_
from sio.compilers.job import run as run_compiler
import sio.executors.unsafe_exec
from sio.testing_utils import str_to_bool
from sio.workers import ft
from sio.workers.util import TemporaryCwd, tempcwd



# Stolen from a sample problem package I used to test the encdec
EXECUTORS = {'unsafe': sio.executors.unsafe_exec}
RLE_TESTS = ['0a', '1']
SOURCES = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sources')


if str_to_bool(os.environ.get('TEST_SIO2JAIL', True)):
    import sio.executors.sio2jail_exec
    EXECUTORS['sio2jail'] = sio.executors.sio2jail_exec


def common_preparations():
    with TemporaryCwd():
        upload_files()
    with TemporaryCwd('compile_chn'):
        run_compiler({
            'source_file': '/rlechn.cpp',
            'compiler': 'system-cpp',
            'out_file': '/rlechn.e'
        })
    with TemporaryCwd('compile_chk'):
        run_compiler({
            'source_file': '/rlechk.cpp',
            'compiler': 'system-cpp',
            'out_file': '/rlechk.e'
        })


def compile_file(file):
    with TemporaryCwd('compile_code'):
        run_compiler({
            'source_file': '/%s.cpp' % file,
            'compiler': 'system-cpp',
            'out_file': '/%s.e' % file,
        })


def in_(a, b, msg=None):
    """Shorthand for 'assert a in b, "%r not in %r" % (a, b)"""
    if a not in b:
        raise AssertionError(msg or "%r not in %r" % (a, b))


def make_run_env(file, test, new_settings=None):
    result = {
        'chn_file': '/rlechn.e',
        'chk_file': '/rlechk.e',
        'exe_file': '/%s.e' % file,
        'hint_file': '/rle%s.hint' % test,
        'in_file': '/rle%s.in' % test,
        'encoder_memory_limit': '65536',
        'encoder_time_limit': 2000,
        'decoder_memory_limit': '65536',
        'decoder_time_limit': 2000,
    }
    if new_settings:
        result.update(new_settings)
    return result


def not_in_(a, b, msg=None):
    """Shorthand for 'assert a not in b, "%r in %r" % (a, b)"""
    if a in b:
        raise AssertionError(msg or "%r in %r" % (a, b))


def print_env(env):
    from pprint import pprint

    pprint(env)


def run_all_configurations(file, func, new_settings=None):
    for execname, executor in EXECUTORS.items():
        for t in RLE_TESTS:
            with TemporaryCwd('run_%s_%s' % (execname, t)):
                print('Running test %s under executor %s' % (t, execname))
                renv = executor.encdec_run(make_run_env(file, t, new_settings(execname, t) if new_settings else None))
                print_env(renv)
                func(execname, t, renv)


def upload_files():
    "Uploads all files from SOURCES to a newly created dummy filetracker"

    # DummyClient operates in the working directory.
    ft.set_instance(DummyClient())
    for path in glob.glob(os.path.join(SOURCES, '*')):
        ft.upload({'path': '/' + os.path.basename(path)}, 'path', path)


def test_encdec_run():
    common_preparations()
    compile_file('rle')
    def check(execname, t, renv):
        not_in_('failed_step', renv)
        eq_(renv['checker_result_percentage'], 100.)
    run_all_configurations('rle', check)


def test_encdec_encoder_timeout():
    common_preparations()
    compile_file('rleloopenc')
    def check(execname, t, renv):
        eq_(renv['failed_step'], 'encoder')
        eq_(renv['encoder_result_code'], 'TLE')
    run_all_configurations('rleloopenc', check)


def test_encdec_encoder_outofmem():
    common_preparations()
    compile_file('rlememenc')
    def check(execname, t, renv):
        eq_(renv['failed_step'], 'encoder')
        in_(renv['encoder_result_code'], ('MLE', 'RE'))
    run_all_configurations('rlememenc', check)


def test_encdec_decoder_timeout():
    common_preparations()
    compile_file('rleloopdec')
    def check(execname, t, renv):
        eq_(renv['failed_step'], 'decoder')
        eq_(renv['decoder_result_code'], 'TLE')
    run_all_configurations('rleloopdec', check)
