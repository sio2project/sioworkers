import glob
import os.path

from filetracker.client.dummy import DummyClient
from sio.assertion_utils import ok_, eq_
from sio.compilers.job import run as run_compiler
from sio.executors.sio2jail_exec import encdec_run
from sio.workers import ft
from sio.workers.util import TemporaryCwd, tempcwd


SOURCES = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sources')


def not_in_(a, b, msg=None):
    """Shorthand for 'assert a not in b, "%r in %r" % (a, b)"""
    if a in b:
        raise AssertionError(msg or "%r in %r" % (a, b))


def print_env(env):
    from pprint import pprint

    pprint(env)


def upload_files():
    "Uploads all files from SOURCES to a newly created dummy filetracker"

    # DummyClient operates in the working directory.
    ft.set_instance(DummyClient())
    for path in glob.glob(os.path.join(SOURCES, '*')):
        ft.upload({'path': '/' + os.path.basename(path)}, 'path', path)


def test_encdec_run():
    with TemporaryCwd():
        upload_files()
    with TemporaryCwd('compile_code'):
        run_compiler({
            'source_file': '/rle.cpp',
            'compiler': 'system-cpp',
            'out_file': '/rle.e'
        })
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
    # Stolen from a sample problem package I used to test the encdec
    with TemporaryCwd('run_0a'):
        renv = encdec_run({
            'chn_file': '/rlechn.e',
            'chk_file': '/rlechk.e',
            'exe_file': '/rle.e',
            'hint_file': '/rle0a.hint',
            'in_file': '/rle0a.in'
        })
        print_env(renv)
        not_in_('failed_step', renv)
        eq_(renv['checker_result_percentage'], 100.)
    with TemporaryCwd('run_1'):
        renv = encdec_run({
            'chn_file': '/rlechn.e',
            'chk_file': '/rlechk.e',
            'exe_file': '/rle.e',
            'hint_file': '/rle1.hint',
            'in_file': '/rle1.in'
        })
        print_env(renv)
        not_in_('failed_step', renv)
        eq_(renv['checker_result_percentage'], 100.)
