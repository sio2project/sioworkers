from __future__ import absolute_import
import logging
import os
import re

from sio.workers import ft
from sio.workers.executors import UnprotectedExecutor, PRootExecutor
from sio.workers.util import tempcwd

logger = logging.getLogger(__name__)

DEFAULT_INGEN_TIME_LIMIT = 600 * 1000  # in ms
DEFAULT_INGEN_MEM_LIMIT = 256 * 2 ** 10  # in KiB
DEFAULT_INGEN_OUTPUT_LIMIT = 10 * 2 ** 10  # in B


def _collect_and_upload(env, path, upload_path, re_string):
    names_re = re.compile(re_string)
    env['collected_files'] = dict()
    for out_file in os.listdir(path):
        if names_re.match(out_file):
            ft.upload(
                env['collected_files'],
                out_file,
                os.path.join(path, out_file),
                '%s/%s' % (upload_path, out_file),
            )


def _run_in_executor(environ, command, executor, **kwargs):
    with executor:
        renv = executor(
            command,
            capture_output=True,
            split_lines=True,
            forward_stderr=True,
            mem_limit=DEFAULT_INGEN_MEM_LIMIT,
            time_limit=DEFAULT_INGEN_TIME_LIMIT,
            output_limit=DEFAULT_INGEN_OUTPUT_LIMIT,
            environ=environ,
            environ_prefix='ingen_',
            **kwargs
        )
        if renv['return_code'] == 0:
            _collect_and_upload(
                renv, tempcwd(), environ['collected_files_path'], environ['re_string']
            )
        return renv


def _run_ingen(environ, use_sandboxes=False):
    command = [tempcwd('ingen')]
    if use_sandboxes:
        executor = PRootExecutor('null-sandbox')
    else:
        executor = UnprotectedExecutor()
    return _run_in_executor(environ, command, executor, ignore_errors=True)


def run(environ):
    """Runs a program, collects the files produced by it and uploads them
    to filetracker.

    Used ``environ`` keys:

    ``exe_file``: the filetracker path to the program

    ``re_string``: a regular expression string used to identify the files
                 which should be uploaded

    ``collected_files_path``: a directory into which the collected files
                            should be uploaded in filetracker

    ``use_sandboxes``: if this key equals ``True``, the program is executed
                     in the PRootExecutor, otherwise the UnsafeExecutor is
                     used

    ``ingen_time_limit``: time limit in ms
                        (optional, the default is 10 mins)

    ``ingen_mem_limit``: memory limit in KiB
                        (optional, the default is 256 MiB)

    ``ingen_output_limit``: output limit in B
                        (optional, the default is 10 KiB)

    On success returns a new environ with a dictionary mapping collected
    files' names to their filetracker paths under ``collected_files``.
    Program's output is returned under the ``stdout`` key. The output is
    trimmed to the first ``ingen_output_limit`` bytes.
    """

    use_sandboxes = environ.get('use_sandboxes', False)
    ft.download(environ, 'exe_file', 'ingen', skip_if_exists=True, add_to_cache=True)
    os.chmod(tempcwd('ingen'), 0o500)
    renv = _run_ingen(environ, use_sandboxes)
    if renv['return_code'] != 0:
        logger.error(
            "Ingen failed!\nEnviron dump: %s\nExecution environ: %s", environ, renv
        )

    return renv
