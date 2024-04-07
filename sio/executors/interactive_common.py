from __future__ import absolute_import
import os
from shutil import rmtree
from threading import Thread
from zipfile import ZipFile, is_zipfile
from sio.workers import ft
from sio.workers.util import decode_fields, replace_invalid_UTF, tempcwd, TemporaryCwd
from sio.workers.file_runners import get_file_runner

import signal
import six
import traceback

import logging
logger = logging.getLogger(__name__)

RESULT_STRING_LENGTH_LIMIT = 1024  # in bytes


def _populate_environ(renv, environ):
    """Takes interesting fields from renv into environ"""
    for key in ('time_used', 'mem_used', 'num_syscalls'):
        environ[key] = renv.get(key, 0)
    for key in ('result_code', 'result_string'):
        environ[key] = renv.get(key, '')
    if 'out_file' in renv:
        environ['out_file'] = renv['out_file']


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

    if environ.get('exec_info', {}).get('mode') == 'output-only':
        renv = _fake_run_as_exe_is_output_file(environ)
    else:
        renv = _run(environ, executor, use_sandboxes)

    _populate_environ(renv, environ)

    # if environ['result_code'] == 'OK' and environ.get('check_output'):
    #     environ = checker.run(environ, use_sandboxes=use_sandboxes)

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
        for fd in (r1, w1, r2, w2):
            os.set_inheritable(fd, True)

        interactor_args = [input_name, tempcwd('out')]
        logger.info(str(interactor_executor))
        logger.info(str(file_executor))

        class InteractiveTaskError(Exception):
            def __init__(self, exception, *args, **kwargs):
                self.msg = "Interactive task failed: " + str(exception) + "\n" + \
                           "args: " + str(args) + "\n" + \
                            "kwargs: " + str(kwargs) + "\n" + \
                            traceback.format_exc()

        class WrapperResult:
            def __init__(self):
                self.res = None
                self.args = None
                self.kwargs = None
                self.exception = None
                self.process_started = False

            def entry(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def set_result(self, res):
                self.res = res

            def get_result(self):
                return self.res

            def set_exception(self, e):
                self.exception = InteractiveTaskError(e, self.args, self.kwargs)

            def has_exception(self):
                return self.exception is not None

            def get_exception(self):
                return self.exception

            def set_started(self):
                self.process_started = True

        interactor_res = WrapperResult()
        sol_res = WrapperResult()

        def thread_wrapper(result, executor, *args, **kwargs):
            result.entry(*args, **kwargs)
            try:
                logger.info("thread_wrapper: " + str(kwargs['in_file']) + " " + str(executor) + " " + str(args) + " " + str(kwargs))
                res = executor(*args, **kwargs)
                result.set_result(res)
            except Exception as e:
                result.set_exception(e)
                logger.error("gaming " + str(kwargs['in_file']) + "\t" +InteractiveTaskError(e, *args, **kwargs).msg)

        with interactor_executor as ie:
            logger.info(tempcwd('out'))
            interactor = Thread(
                target=thread_wrapper,
                args=(
                    interactor_res,
                    ie,
                    tempcwd(interactor_filename),
                    interactor_args,
                ),
                kwargs = dict(
                    stdin=r2,
                    stdout=w1,
                    ignore_errors=False,
                    extra_ignore_errors=(141,),     # SIGPIPE
                    environ=environ,
                    environ_prefix='exec_',
                    pass_fds=(r2, w1),
                    cwd=tempcwd(),
                    process_status=interactor_res,
                    in_file=environ['in_file'],
                )
            )

        with file_executor as fe:
            exe = Thread(
                target=thread_wrapper,
                args=(
                    sol_res,
                    fe,
                    tempcwd(exe_filename),
                    [],
                ),
                kwargs=dict(
                    stdin=r1,
                    stdout=w2,
                    ignore_errors=False,
                    extra_ignore_errors=(141,),     # SIGPIPE
                    environ=environ,
                    environ_prefix='exec_',
                    pass_fds=(r1, w2),
                    cwd=tempcwd(),
                    process_status=sol_res,
                    in_file=environ['in_file'],
                )
            )

        logger.info("Starting threads " + environ['in_file'])
        exe.start()
        logger.info("Started exe " + environ['in_file'])
        interactor.start()
        logger.info("Started interactor " + environ['in_file'])

        # Very beautiful hack
        while not interactor_res.process_started or not sol_res.process_started:
            pass
        for fd in (r1, w1, r2, w2):
            os.close(fd)
        logger.info("Closed fds " + environ['in_file'])

        exe.join()
        logger.info("exe joined " + environ['in_file'])
        interactor.join()
        logger.info("interactor joined " + environ['in_file'])

        if interactor_res.has_exception():
            raise interactor_res.get_exception()
        if sol_res.has_exception():
            raise sol_res.get_exception()

        irenv = interactor_res.get_result()
        renv = sol_res.get_result()

        logger.info(tempcwd('out'))
        with open(tempcwd('out'), 'rb') as result_file:
            interactor_out = [line.rstrip() for line in result_file.readlines()]

        # logger.info(str(interactor_out))
        # logger.info("irenv: " + str(irenv))
        # logger.info("renv: " + str(renv))

        sol_sig = renv.get('exit_signal', None)
        inter_sig = irenv.get('exit_signal', None)
        sigpipe = signal.SIGPIPE.value

        if sol_sig == sigpipe and not interactor_out:
            renv['result_code'] = 'SE'
            renv['result_string'] = 'checker exited prematurely'
        elif inter_sig == sigpipe:
            renv['result_code'] = 'WA'
            renv['result_string'] = 'solution exited prematurely'
        else:
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
