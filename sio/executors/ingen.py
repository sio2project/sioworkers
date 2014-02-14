import os.path
import logging
import re

from sio.workers import ft
from sio.workers.executors import UnprotectedExecutor, PRootExecutor, \
        ExecError

logger = logging.getLogger(__name__)

DEFAULT_INGEN_TIME_LIMIT = 30000  # in ms
DEFAULT_INGEN_MEM_LIMIT = 256 * 2**10  # in KiB

def _collect_and_upload(env, path, re_string):
    names_re = re.compile(re_string)
    env['collected_files'] = dict()
    for out_file in os.listdir(path):
        if names_re.match(out_file):
            ft.upload(env['collected_files'], out_file, out_file,
                    '/%s' % out_file)

def _run_in_executor(environ, command, executor, **kwargs):
    with executor:
        renv = executor(command,
            capture_output=True, split_lines=True, forward_stderr=True,
            mem_limit=DEFAULT_INGEN_MEM_LIMIT,
            time_limit=DEFAULT_INGEN_TIME_LIMIT,
            environ=environ, environ_prefix='ingen_', **kwargs)
        _collect_and_upload(renv, os.getcwd(), environ['re_string'])
        return renv

def _run_ingen(environ, use_sandboxes=False):
    command = ['./ingen']
    if use_sandboxes:
        executor = PRootExecutor('exec-sandbox')
    else:
        executor = UnprotectedExecutor()
    return _run_in_executor(environ, command, executor, ignore_return=True)

def run(environ):
    use_sandboxes = environ.get('use_sandboxes', False)
    ft.download(environ, 'exe_file', 'ingen', skip_if_exists=True,
            add_to_cache=True)
    os.chmod('ingen', 0700)
    try:
        renv = _run_ingen(environ, use_sandboxes)
    except ExecError as e:
        logger.error('Ingen failed! %s', e)
        logger.error('Environ dump: %s', environ)
        return environ

    return renv
