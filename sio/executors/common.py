import os
from sio.workers import ft
from sio.workers.util import replace_invalid_UTF

from sio.executors import checker

def _populate_environ(renv, environ):
    """Takes interesting fields from renv into environ"""
    for key in ('time_used', 'mem_used', 'num_syscalls'):
        environ[key] = renv.get(key, 0)
    for key in ('result_code', 'result_string'):
        environ[key] = renv.get(key, '')

def run(environ, executor, safe_check=True):
    """
    Common code for executors.

    :param: environ Recipe to pass to `filetracker` and `sio.workers.executors`
                    For all supported options, see the global documentation for
                    `sio.workers.executors` and prefix them with ``exec_``.
    :param: executor Executor instance used for executing commands.
    :param: safe_check Enables safe checking output corectness.
                       See `sio.executors.checkers`. True by default.
    """
    ft.download(environ, 'exe_file', 'exe', add_to_cache=True)
    os.chmod('exe', 0700)
    ft.download(environ, 'in_file', 'in', add_to_cache=True)

    with executor as e:
        with open('in', 'rb') as inf:
            with open('out', 'wb') as outf:
                renv = e(['./exe'], stdin=inf, stdout=outf, ignore_errors=True,
                            environ=environ, environ_prefix='exec_')

    _populate_environ(renv, environ)

    if renv['result_code'] == 'OK' and environ.get('check_output'):
        environ = checker.run(environ, no_sandbox=not safe_check)

    for key in ('result_code', 'result_string'):
        environ[key] = replace_invalid_UTF(environ[key])

    if 'out_file' in environ:
        ft.upload(environ, 'out_file', 'out',
            to_remote_store=environ.get('upload_out', False))

    return environ
