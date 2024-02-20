from __future__ import absolute_import
import os.path
import logging
import tempfile
import six
import re

from sio.workers import ft
from sio.workers.executors import (
    UnprotectedExecutor,
    SandboxExecutor,
    ExecError,
    PRootExecutor,
)
from sio.workers.util import tempcwd

logger = logging.getLogger(__name__)

DEFAULT_CHECKER_TIME_LIMIT = 30000  # in ms
DEFAULT_CHECKER_MEM_LIMIT = 256 * 2 ** 10  # in KiB
RESULT_STRING_LENGTH_LIMIT = 1024  # in bytes


class CheckerError(Exception):
    pass


def _run_in_executor(env, command, executor, **kwargs):
    with executor:
        return executor(
            command,
            capture_output=True,
            split_lines=True,
            mem_limit=DEFAULT_CHECKER_MEM_LIMIT,
            time_limit=DEFAULT_CHECKER_TIME_LIMIT,
            environ=env,
            environ_prefix='checker_',
            **kwargs
        )


def _run_diff(env):
    renv = _run_in_executor(
        env,
        ['diff', '-b', '-q', 'out', 'hint'],
        UnprotectedExecutor(),
        extra_ignore_errors=(1,),
    )
    return renv['return_code'] and ['WA'] or ['OK']


def _run_checker(env, use_sandboxes=False):
    command = ['./chk', 'in', 'out', 'hint']

    def execute_checker(with_stderr=False, stderr=None):
        if env.get('untrusted_checker', False) and use_sandboxes:
            return _run_in_executor(
                env,
                command,
                PRootExecutor('null-sandbox'),
                ignore_return=True,
                forward_stderr=with_stderr,
                stderr=stderr,
            )
        else:
            return _run_in_executor(
                env,
                command,
                UnprotectedExecutor(),
                ignore_errors=True,
                forward_stderr=with_stderr,
                stderr=stderr,
            )

    with tempfile.TemporaryFile() as stderr_file:
        renv = execute_checker(stderr=stderr_file)
        if renv['return_code'] >= 2:
            stderr_file.seek(0)
            stderr = stderr_file.read()
            raise CheckerError(
                'Checker returned code(%d) >= 2. Checker stdout: '
                '"%s", stderr: "%s". Checker environ dump: %s'
                % (renv['return_code'], renv['stdout'], stderr, env)
            )

    return renv['stdout']


def _run_compare(env):
    e = SandboxExecutor('exec-sandbox')
    renv = _run_in_executor(
        env, [os.path.join('bin', 'compare'), 'hint', 'out'], e, ignore_errors=True
    )
    return renv['stdout']


def _limit_length(s):
    if len(s) > RESULT_STRING_LENGTH_LIMIT:
        suffix = b'[...]'
        return s[: max(0, RESULT_STRING_LENGTH_LIMIT - len(suffix))] + suffix
    return s


def run(environ, use_sandboxes=True):
    ft.download(environ, 'out_file', 'out', skip_if_exists=True)
    ft.download(environ, 'hint_file', 'hint', add_to_cache=True)

    try:
        if environ.get('chk_file'):
            ft.download(
                environ, 'in_file', 'in', skip_if_exists=True, add_to_cache=True
            )
            ft.download(environ, 'chk_file', 'chk', add_to_cache=True)
            os.chmod(tempcwd('chk'), 0o700)

            output = _run_checker(environ, use_sandboxes)
        elif use_sandboxes:
            output = _run_compare(environ)
        else:
            output = _run_diff(environ)
    except (CheckerError, ExecError) as e:
        logger.error('Checker failed! %s', e)
        logger.error('Environ dump: %s', environ)
        raise SystemError(e)

    while len(output) < 3:
        output.append('')

    if six.ensure_binary(output[0]) == b'OK':
        environ['result_code'] = 'OK'
        if output[1]:
            environ['result_string'] = _limit_length(output[1])
        environ['result_percentage'] = output_to_fraction(output[2])
    else:
        environ['result_code'] = 'WA'
        environ['result_string'] = _limit_length(output[1])
        environ['result_percentage'] = (0, 1)
    return environ


def output_to_fraction(output_str):
    if not output_str:
        return 100, 1
    output_is_float = re.match(r"[0-9]+\.[0-9]*", output_str)
    output_is_percent = re.match(r"[0-9]+", output_str)
    output_is_fraction = re.match(r"[0-9]+ [0-9]+", output_str)
    if output_is_float:
        return float_to_fraction(output_str)
    elif output_is_percent:
        return int(output_str), 1
    elif output_is_fraction:
        return tuple(output_str.split(" "))
    else:
        raise CheckerError(
            'Invalid checker output, expected float, percent or fraction, got "%s"'
            % output_str
        )


def float_to_fraction(float_str):
    nominator = int(''.join(filter(str.isdigit, float_str)))
    denominator = 10 ** (len(float_str) - float_str.find('.') - 1)
    return nominator, denominator
