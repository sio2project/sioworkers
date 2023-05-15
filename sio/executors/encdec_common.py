from __future__ import absolute_import
import os
import logging
from shutil import copy2, rmtree
import tempfile
from zipfile import ZipFile, is_zipfile
from sio.executors.checker import _limit_length
from sio.executors.common import _run_core
from sio.workers import ft
from sio.workers.executors import ExecError, PRootExecutor, UnprotectedExecutor
from sio.workers.util import decode_fields, replace_invalid_UTF, tempcwd, TemporaryCwd
from sio.workers.file_runners import get_file_runner

logger = logging.getLogger(__name__)


DEFAULT_SUPPLEMENTARY_TIME_LIMIT = 30000  # in ms
DEFAULT_SUPPLEMENTARY_MEM_LIMIT = 268 * 2**10  # in KiB


class ChannelError(Exception):
    pass


class CheckerError(Exception):
    pass


def _populate_environ(renv, environ, prefix):
    """Takes interesting fields from renv into environ"""
    for key in (
        "time_used",
        "mem_used",
        "num_syscalls",
        "result_code",
        "result_string",
    ):
        if key in renv:
            environ[prefix + key] = renv[key]


def _run_supplementary(env, command, executor, environ_prefix, **kwargs):
    with executor:
        return executor(
            command,
            capture_output=True,
            split_lines=True,
            mem_limit=DEFAULT_SUPPLEMENTARY_MEM_LIMIT,
            time_limit=DEFAULT_SUPPLEMENTARY_TIME_LIMIT,
            environ=env,
            environ_prefix=environ_prefix,
            **kwargs
        )


def _run_encoder(environ, file_executor, exe_filename, use_sandboxes):
    ft.download(environ, "in_file", "enc_in", add_to_cache=True)
    return _run_core(
        environ,
        file_executor,
        tempcwd("enc_in"),
        tempcwd("enc_out"),
        tempcwd(exe_filename),
        "encoder_",
        use_sandboxes,
    )


def _run_channel_core(env, result_file, checker_file, use_sandboxes=False):
    command = [
        "./chn",
        "enc_in",
        "enc_out",
        "hint",
        str(result_file.fileno()),
        str(checker_file.fileno()),
    ]

    def execute_channel(with_stderr=False, stderr=None):
        return _run_supplementary(
            env,
            command,
            PRootExecutor("null-sandbox")
            if env.get("untrusted_channel", False) and use_sandboxes
            else UnprotectedExecutor(),
            "channel_",
            ignore_errors=True,
            forward_stderr=with_stderr,
            stderr=stderr,
            pass_fds=(result_file.fileno(), checker_file.fileno()),
        )

    with tempfile.TemporaryFile() as stderr_file:
        renv = execute_channel(stderr=stderr_file)
        if renv["return_code"] >= 2:
            stderr_file.seek(0)
            stderr = stderr_file.read()
            raise ChannelError(
                "Channel returned code(%d) >= 2. Channel stdout: "
                '"%s", stderr: "%s". Channel environ dump: %s'
                % (renv["return_code"], renv["stdout"], stderr, env)
            )

    return renv["stdout"]


def _run_channel(environ, use_sandboxes=False):
    ft.download(environ, "hint_file", "hint", add_to_cache=True)
    ft.download(environ, "chn_file", "chn", add_to_cache=True)
    os.chmod(tempcwd("chn"), 0o700)
    result_filename = tempcwd("dec_in")
    checker_filename = tempcwd("chn_out")

    try:
        with open(result_filename, "wb") as result_file, open(
            checker_filename, "wb"
        ) as checker_file:
            output = _run_channel_core(
                environ, result_file, checker_file, use_sandboxes
            )
    except (ChannelError, ExecError) as e:
        logger.error("Channel failed! %s", e)
        logger.error("Environ dump: %s", environ)
        raise SystemError(e)

    while len(output) < 3:
        output.append(b"")

    if output[0] == b"OK":
        environ["channel_result_code"] = "OK"
        if output[1]:
            environ["channel_result_string"] = _limit_length(output[1]).decode("utf-8")
        return True
    else:
        environ["failed_step"] = "channel"
        environ["channel_result_code"] = "WA"
        environ["channel_result_string"] = _limit_length(output[1]).decode("utf-8")
        return False


def _run_decoder(environ, file_executor, exe_filename, use_sandboxes):
    return _run_core(
        environ,
        file_executor,
        tempcwd("dec_in"),
        tempcwd("dec_out"),
        tempcwd(exe_filename),
        "decoder_",
        use_sandboxes,
    )


def _run_checker_core(env, use_sandboxes=False):
    command = ["./chk", "enc_in", "hint", "chn_out", "dec_out"]

    def execute_checker(with_stderr=False, stderr=None):
        return _run_supplementary(
            env,
            command,
            PRootExecutor("null-sandbox")
            if env.get("untrusted_checker", False) and use_sandboxes
            else UnprotectedExecutor(),
            "checker_",
            ignore_errors=True,
            forward_stderr=with_stderr,
            stderr=stderr,
        )

    with tempfile.TemporaryFile() as stderr_file:
        renv = execute_checker(stderr=stderr_file)
        if renv["return_code"] >= 2:
            stderr_file.seek(0)
            stderr = stderr_file.read()
            raise CheckerError(
                "Checker returned code(%d) >= 2. Checker stdout: "
                '"%s", stderr: "%s". Checker environ dump: %s'
                % (renv["return_code"], renv["stdout"], stderr, env)
            )

    return renv["stdout"]


def _run_checker(environ, use_sandboxes=False):
    ft.download(environ, "chk_file", "chk", add_to_cache=True)
    os.chmod(tempcwd("chk"), 0o700)

    try:
        output = _run_checker_core(environ, use_sandboxes)
    except (ChannelError, ExecError) as e:
        logger.error("Checker failed! %s", e)
        logger.error("Environ dump: %s", environ)
        raise SystemError(e)

    while len(output) < 3:
        output.append(b"")

    if output[0] == b"OK":
        environ["checker_result_code"] = "OK"
        if output[1]:
            environ["checker_result_string"] = _limit_length(output[1]).decode("utf-8")
        environ["checker_result_percentage"] = float(output[2] or 100)
        return True
    else:
        environ["failed_step"] = "checker"
        environ["checker_result_code"] = "WA"
        environ["checker_result_string"] = _limit_length(output[1]).decode("utf-8")
        environ["checker_result_percentage"] = 0
        return False


def _run_decoder_hide_files(environ, file_executor, exe_filename, use_sandboxes, orig_dir):
    # We now have quite a lot of interes
    # be nice if some decoder read them.
    with TemporaryCwd() as new_dir:
        # Copy the executable and input
        for f in 'dec_in', exe_filename:
            copy2(os.path.join(orig_dir, f), tempcwd(f))

        renv = _run_decoder(environ, file_executor, exe_filename, use_sandboxes)

        # Copy the output
        for f in 'dec_out',:
            copy2(tempcwd(f), os.path.join(orig_dir, f))

    return renv


def run(environ, executor, use_sandboxes=True):
    """
    Common code for executors.

    :param: environ Recipe to pass to `filetracker` and `sio.workers.executors`
                    For all supported options, see the global documentation for
                    `sio.workers.executors` and prefix them with ``encoder_``
                    or ``decoder_``.
    :param: executor Executor instance used for executing commands.
    :param: use_sandboxes Enables safe checking output correctness.
                          See `sio.executors.checkers`. True by default.
    """

    file_executor = get_file_runner(executor, environ)
    exe_filename = file_executor.preferred_filename()

    ft.download(environ, "exe_file", exe_filename, add_to_cache=True)
    os.chmod(tempcwd(exe_filename), 0o700)

    encoder_environ = environ.copy()
    renv = _run_encoder(encoder_environ, file_executor, exe_filename, use_sandboxes)
    _populate_environ(renv, environ, "encoder_")

    if renv["result_code"] != "OK":
        environ["failed_step"] = "encoder"
        return environ

    if not _run_channel(environ, use_sandboxes):
        return environ

    renv = _run_decoder_hide_files(environ, file_executor, exe_filename, use_sandboxes, tempcwd())
    _populate_environ(renv, environ, "decoder_")

    if renv["result_code"] != "OK":
        environ["failed_step"] = "decoder"
        return environ

    _run_checker(environ, use_sandboxes)

    return environ
