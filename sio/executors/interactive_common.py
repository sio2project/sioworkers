from __future__ import absolute_import
import os
from shutil import rmtree
from threading import Thread
from zipfile import ZipFile, is_zipfile

from sio.executors.common import _extract_input_if_zipfile, _populate_environ
from sio.workers import ft
from sio.workers.util import decode_fields, replace_invalid_UTF, tempcwd, TemporaryCwd
from sio.workers.file_runners import get_file_runner

import signal
import six
import traceback

import logging
logger = logging.getLogger(__name__)

DEFAULT_INTERACTOR_TIME_LIMIT = 30000  # in ms
DEFAULT_INTERACTOR_MEM_LIMIT = 256 * 2 ** 10  # in KiB
RESULT_STRING_LENGTH_LIMIT = 1024  # in bytes


def _limit_length(s):
    if len(s) > RESULT_STRING_LENGTH_LIMIT:
        suffix = b'[...]'
        return s[: max(0, RESULT_STRING_LENGTH_LIMIT - len(suffix))] + suffix
    return s


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

    renv = _run(environ, executor, use_sandboxes)

    _populate_environ(renv, environ)

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


def _fill_result(renv, irenv, interactor_out):
    sol_sig = renv.get('exit_signal', None)
    inter_sig = irenv.get('exit_signal', None)
    sigpipe = signal.SIGPIPE.value

    logger.info(renv)
    logger.info(irenv)

    if irenv['result_code'] != 'OK' and inter_sig != sigpipe:
        renv['result_code'] = 'SE'
    elif renv['result_code'] != 'OK' and sol_sig != sigpipe:
        return
    elif len(interactor_out) == 0:
        renv['result_code'] = 'SE'
        renv['result_string'] = 'invalid interactor output'
    elif inter_sig == sigpipe:
        renv['result_code'] = 'WA'
        renv['result_string'] = 'solution exited prematurely'
    else:
        renv['result_string'] = ''
        if six.ensure_binary(interactor_out[0]) == b'OK':
            renv['result_code'] = 'OK'
            if interactor_out[1]:
                renv['result_string'] = _limit_length(interactor_out[1])
            renv['result_percentage'] = float(interactor_out[2] or 100)
        else:
            renv['result_code'] = 'WA'
            if interactor_out[1]:
                renv['result_string'] = _limit_length(interactor_out[1])
            renv['result_percentage'] = 0


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

    zipdir = tempcwd('in_dir')
    os.mkdir(zipdir)
    try:
        input_name = _extract_input_if_zipfile(input_name, zipdir)

        r1, w1 = os.pipe()
        r2, w2 = os.pipe()
        for fd in (r1, w1, r2, w2):
            os.set_inheritable(fd, True)

        interactor_args = [input_name, tempcwd('out')]
        logger.info(str(interactor_executor))
        logger.info(str(file_executor))

        irenv = {}
        renv = {}

        with interactor_executor as ie:
            logger.info(tempcwd('out'))
            interactor = Thread(
                target=ie,
                args=(
                    tempcwd(interactor_filename),
                    interactor_args,
                ),
                kwargs = dict(
                    stdin=r2,
                    stdout=w1,
                    ignore_errors=True,
                    environ=environ,
                    environ_prefix='interactor_',
                    mem_limit=DEFAULT_INTERACTOR_MEM_LIMIT,
                    time_limit=DEFAULT_INTERACTOR_TIME_LIMIT,
                    pass_fds=(r2, w1),
                    close_passed_fd=True,
                    cwd=tempcwd(),
                    in_file=environ['in_file'],
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
                    close_passed_fd=True,
                    cwd=tempcwd(),
                    in_file=environ['in_file'],
                    ret_env=renv,
                )
            )

        exe.start()
        interactor.start()

        exe.join()
        interactor.join()

        with open(tempcwd('out'), 'rb') as result_file:
            interactor_out = [line.rstrip() for line in result_file.readlines()]

        while len(interactor_out) < 3:
            interactor_out.append(b'')

        _fill_result(renv, irenv, interactor_out)
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
