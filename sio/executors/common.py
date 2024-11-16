from __future__ import absolute_import
import os
from shutil import rmtree
from zipfile import ZipFile, is_zipfile
from sio.archive_utils import Archive, UnrecognizedArchiveFormat, UnsafeArchive
from sio.workers import ft
from sio.workers.util import decode_fields, replace_invalid_UTF, tempcwd
from sio.workers.file_runners import get_file_runner

from sio.executors import checker
import six


import logging
logger = logging.getLogger(__name__)

def _populate_environ(renv, environ):
    """Takes interesting fields from renv into environ"""
    for key in ('time_used', 'mem_used', 'num_syscalls'):
        environ[key] = renv.get(key, 0)
    for key in ('result_code', 'result_string'):
        environ[key] = renv.get(key, '')
    if 'out_file' in renv:
        environ['out_file'] = renv['out_file']


def _extract_input_if_zipfile(input_name, zipdir):
    if is_zipfile(input_name):
        try:
            # If not a zip file, will pass it directly to exe
            with ZipFile(tempcwd('in'), 'r') as f:
                if len(f.namelist()) != 1:
                    raise Exception("Archive should have only one file.")

                f.extract(f.namelist()[0], zipdir)
                input_name = os.path.join(zipdir, f.namelist()[0])
        # zipfile throws some undocumented exceptions
        except Exception as e:
            raise Exception("Failed to open archive: " + six.text_type(e))

    return input_name


@decode_fields(['result_string'])
def run(environ, executor, use_sandboxes=True):
    """
    Common code for executors.

    :param: environ Recipe to pass to `filetracker` and `sio.workers.executors`
                    For all supported options, see the global documentation for
                    `sio.workers.executors` and prefix them with ``exec_``.
    :param: executor Executor instance used for executing commands.
    :param: use_sandboxes Enables safe checking output correctness.
                       See `sio.executors.checkers`. True by default.
    """

    if environ.get('exec_info', {}).get('mode') == 'output-only':
        renv = _fake_run_as_exe_is_output_file(environ)
    else:
        renv = _run(environ, executor, use_sandboxes)

    _populate_environ(renv, environ)

    if environ['result_code'] == 'OK' and environ.get('check_output'):
        environ = checker.run(environ, use_sandboxes=use_sandboxes)

    for key in ('result_code', 'result_string'):
        environ[key] = replace_invalid_UTF(environ[key])

    if 'out_file' in environ:
        ft.upload(
            environ,
            'out_file',
            tempcwd('out'),
            to_remote_store=environ.get('upload_out', False),
        )

    return environ


def _run(environ, executor, use_sandboxes):
    input_name = tempcwd('in')

    file_executor = get_file_runner(executor, environ)
    exe_filename = file_executor.preferred_filename()

    ft.download(environ, 'exe_file', exe_filename, add_to_cache=True)
    os.chmod(tempcwd(exe_filename), 0o700)
    ft.download(environ, 'in_file', input_name, add_to_cache=True)

    zipdir = tempcwd('in_dir')
    os.mkdir(zipdir)
    try:
        input_name = _extract_input_if_zipfile(input_name, zipdir)

        with file_executor as fe:
            with open(input_name, 'rb') as inf:
                # Open output file in append mode to allow appending
                # only to the end of the output file. Otherwise,
                # a contestant's program could modify the middle of the file.
                with open(tempcwd('out'), 'ab') as outf:
                    renv = fe(
                        tempcwd(exe_filename),
                        [],
                        stdin=inf,
                        stdout=outf,
                        ignore_errors=True,
                        environ=environ,
                        environ_prefix='exec_',
                    )

    finally:
        rmtree(zipdir)

    return renv


def _fake_run_as_exe_is_output_file(environ):
    try:
        ft.download(environ, 'exe_file', tempcwd('outs_archive'))
        archive = Archive.get(tempcwd('outs_archive'))
        problem_short_name = environ['problem_short_name']
        test_name = f'{problem_short_name}{environ["name"]}.out'
        logger.info('Archive with outs provided')
        if test_name in archive.filenames():
            archive.extract(test_name, to_path=tempcwd())
            os.rename(os.path.join(tempcwd(), test_name), tempcwd('out'))
        else:
            logger.info(f'Output {test_name} not found in archive')
            return {
                'result_code': 'WA',
                'result_string': 'output not provided',
            }
    except UnrecognizedArchiveFormat as e:
        # regular text file
        logger.info('Text out provided')
        # later code expects 'out' file to be present after compilation
        ft.download(environ, 'exe_file', tempcwd('out'))
    except UnsafeArchive as e:
        logger.warning(six.text_type(e))
    return {
        # 'result_code' is left by executor, as executor is not used
        # this variable has to be set manually
        'result_code': 'OK',
        'result_string': 'ok',
    }

