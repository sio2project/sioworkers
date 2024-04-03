from __future__ import absolute_import
import os
from shutil import rmtree
from threading import Thread
from zipfile import ZipFile, is_zipfile
from sio.workers import ft
from sio.workers.util import decode_fields, replace_invalid_UTF, tempcwd
from sio.workers.file_runners import get_file_runner

from sio.executors import checker
import signal
import six


def _populate_environ(renv, environ):
    """Takes interesting fields from renv into environ"""
    for key in ('time_used', 'mem_used', 'num_syscalls'):
        environ[key] = renv.get(key, 0)
    for key in ('result_code', 'result_string'):
        environ[key] = renv.get(key, '')
    if 'out_file' in renv:
        environ['out_file'] = renv['out_file']


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
    interactor_env = environ.copy()
    interactor_env['exe_file'] = interactor_env['interactor_file']
    interactor_executor = get_file_runner(executor, interactor_env)
    exe_filename = file_executor.preferred_filename()
    interactor_filename = 'soc'

    ft.download(environ, 'exe_file', exe_filename, add_to_cache=True)
    os.chmod(tempcwd(exe_filename), 0o700)
    ft.download(environ, 'interactor_file', interactor_filename, add_to_cache=True)
    os.chmod(tempcwd(interactor_filename), 0o700)
    ft.download(environ, 'in_file', input_name, add_to_cache=True)
    ft.download(environ, 'out_file', 'out', skip_if_exists=True)
    ft.download(environ, 'hint_file', 'hint', add_to_cache=True)

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

        r1, w1 = os.pipe()
        r2, w2 = os.pipe()
        os.set_inheritable(r1, True)
        os.set_inheritable(w1, True)
        os.set_inheritable(r2, True)
        os.set_inheritable(w2, True)

        irenv = {}
        renv = {}
        interactor_command = [tempcwd(interactor_filename), input_name, 'out', 'hint']
        with interactor_executor as ie:
            with open(tempcwd('out'), 'ab') as outf:
                interactor = Thread(
                    target=ie,
                    args=(
                        interactor_command,
                        [],
                    ),
                    kwargs=dict(
                        stdin=r2,
                        stdout=w1,
                        stderr=outf,
                        ignore_errors=True,
                        environ=environ,
                        environ_prefix='exec_',
                        pass_fds=(r2, w1),
                        wait=False,
                        ret_env=irenv,
                    )
                )

        with file_executor as fe:
            exe = Thread(
                target=fe,
                args=(
                    tempcwd(exe_filename),
                    [],
                ),
                kwargs=dict(
                    stdin=r1,
                    stdout=w2,
                    ignore_errors=True,
                    environ=environ,
                    environ_prefix='exec_',
                    pass_fds=(r1, w2),
                    ret_env=renv,
                )
            )

        os.close(r1)
        os.close(w1)
        os.close(r2)
        os.close(w2)
        exe.start()
        interactor.start()
        exe.join()
        interactor.join()
        
        sol_sig = renv.get('exit_signal', None)
        inter_sig = irenv.get('exit_signal', None)
        sigpipe = signal.SIGPIPE.value
        
        if sol_sig == sigpipe:
            renv['result_code'] = 'SE'
            renv['result_string'] = 'Checker exited prematurely. ' 
        elif inter_sig == sigpipe:
            renv['result_code'] = 'SE'
            renv['result_string'] = 'Solution exited prematurely'
    finally:
        rmtree(zipdir)

    return renv


def _fake_run_as_exe_is_output_file(environ):
    # later code expects 'out' file to be present after compilation
    ft.download(environ, 'exe_file', tempcwd('out'))
    return {
        # copy filetracker id of 'exe_file' as 'out_file' (thanks to that checker will grab it)
        'out_file': environ['exe_file'],
        # 'result_code' is left by executor, as executor is not used
        # this variable has to be set manually
        'result_code': 'OK',
        'result_string': 'ok',
    }
