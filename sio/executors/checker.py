import os.path
import logging

from sio.workers import ft
from sio.workers.executors import UnprotectedExecutor, SandboxExecutor, \
        ExecError, SupervisedExecutor
from sio.workers.util import tempcwd

logger = logging.getLogger(__name__)

DEFAULT_CHECKER_TIME_LIMIT = 30000  # in ms
DEFAULT_CHECKER_MEM_LIMIT = 256 * 2**10  # in KiB

class CheckerError(Exception):
    pass

def _run_in_executor(env, command, executor, **kwargs):
    with executor:
        return executor(command,
            capture_output=True, split_lines=True,
            mem_limit=DEFAULT_CHECKER_MEM_LIMIT,
            time_limit=DEFAULT_CHECKER_TIME_LIMIT,
            environ=env, environ_prefix='checker_', **kwargs)

def _run_diff(env):
    renv = _run_in_executor(env, ['diff', '-b', '-q', 'out', 'hint'],
            UnprotectedExecutor(), extra_ignore_errors=(1,))
    return renv['return_code'] and ['WA'] or ['OK']

def _run_checker(env, use_sandboxes=False):
    command = ['./chk', 'in', 'out', 'hint']
    if env.get('untrusted_checker', False) and use_sandboxes:
        renv = _run_in_executor(env, command,
                SupervisedExecutor(allow_local_open=True,
                        use_program_return_code=True), ignore_return=False,
                extra_ignore_errors=[1])
    else:
        renv = _run_in_executor(env, command, UnprotectedExecutor(),
                ignore_errors=True)

    if renv['return_code'] >= 2:
        raise CheckerError(
                'Checker returned code(%d) >= 2. Checker environ dump: %s' \
                        % (renv['return_code'], env))

    return renv['stdout']

def _run_compare(env):
    e = SandboxExecutor('exec-sandbox')
    renv = _run_in_executor(env, [os.path.join('bin', 'compare'),
            'hint', 'out'], e, ignore_errors=True)
    return renv['stdout']

def run(environ, use_sandboxes=True):
    ft.download(environ, 'out_file', 'out', skip_if_exists=True)
    ft.download(environ, 'hint_file', 'hint', add_to_cache=True)

    try:
        if environ.get('chk_file'):
            ft.download(environ, 'in_file', 'in', skip_if_exists=True,
                    add_to_cache=True)
            ft.download(environ, 'chk_file', 'chk', add_to_cache=True)
            os.chmod(tempcwd('chk'), 0700)

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
    if output[0] == 'OK':
        environ['result_code'] = 'OK'
        if output[1]:
            environ['result_string'] = output[1]
        environ['result_percentage'] = float(output[2] or 100)
    else:
        environ['result_code'] = 'WA'
        environ['result_string'] = output[1]
        environ['result_percentage'] = 0
    return environ
