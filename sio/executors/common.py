from __future__ import absolute_import
import os
from shutil import rmtree
from zipfile import ZipFile, is_zipfile
from sio.workers import ft
from sio.workers.util import decode_fields, replace_invalid_UTF, tempcwd
from sio.workers.file_runners import get_file_runner

from sio.executors import checker
import six

def _populate_environ(renv, environ):
    """Takes interesting fields from renv into environ"""
    for key in ('time_used', 'mem_used', 'num_syscalls'):
        environ[key] = renv.get(key, 0)
    for key in ('result_code', 'result_string'):
        environ[key] = renv.get(key, '')


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
    input_name = tempcwd('in')

    file_executor = get_file_runner(executor, environ)
    exe_filename = file_executor.preferred_filename()

    ft.download(environ, 'exe_file', exe_filename, add_to_cache=True)
    os.chmod(tempcwd(exe_filename), 0o700)
    ft.download(environ, 'in_file', input_name, add_to_cache=True)

    zipdir = tempcwd('in_dir')
    os.mkdir(zipdir)
    try:
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

        with file_executor as fe:
            with open(input_name, 'rb') as inf:
                # Open output file in append mode to allow appending
                # only to the end of the output file. Otherwise,
                # a contestant's program could modify the middle of the file.
                with open(tempcwd('out'), 'ab') as outf:
                    renv = fe(tempcwd(exe_filename), [],
                              stdin=inf, stdout=outf, ignore_errors=True,
                              environ=environ, environ_prefix='exec_')

        _populate_environ(renv, environ)

        if renv['result_code'] == 'OK' and environ.get('check_output'):
            environ = checker.run(environ, use_sandboxes=use_sandboxes)

        for key in ('result_code', 'result_string'):
            environ[key] = replace_invalid_UTF(environ[key])

        if 'out_file' in environ:
            ft.upload(environ, 'out_file', tempcwd('out'),
                to_remote_store=environ.get('upload_out', False))
    finally:
        rmtree(zipdir)

    return environ
