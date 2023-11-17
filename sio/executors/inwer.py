from __future__ import absolute_import
import logging
import os

from sio.workers import ft
from sio.workers.executors import DetailedUnprotectedExecutor, SupervisedExecutor
from sio.workers.util import tempcwd

logger = logging.getLogger(__name__)

DEFAULT_INWER_TIME_LIMIT = 300000  # in ms
DEFAULT_INWER_MEM_LIMIT = 256 * 2 ** 10  # in KiB
DEFAULT_INWER_OUTPUT_LIMIT = 10 * 2 ** 10  # in B


def _run_in_executor(environ, command, executor, **kwargs):
    with executor:
        with open(tempcwd('in'), 'rb') as inf:
            return executor(
                command,
                stdin=inf,
                capture_output=True,
                split_lines=True,
                forward_stderr=True,
                mem_limit=DEFAULT_INWER_MEM_LIMIT,
                time_limit=DEFAULT_INWER_TIME_LIMIT,
                output_limit=DEFAULT_INWER_OUTPUT_LIMIT,
                environ=environ,
                environ_prefix='inwer_',
                **kwargs
            )


def _run_inwer(environ, use_sandboxes=False):
    command = [tempcwd('inwer')]
    if 'in_file_name' in environ:
        command.append(environ['in_file_name'])
    if use_sandboxes:
        executor = SupervisedExecutor()
    else:
        executor = DetailedUnprotectedExecutor()
    return _run_in_executor(environ, command, executor, ignore_errors=True)


def run(environ):
    """Runs a verifying program and returns its output.

    Used ``environ`` keys:

    ``exe_file``: the filetracker path to the program

    ``in_file``: the file redirected to the program's stdin

    ``in_file_name``: the name of the input file. It's passed to inwer as
                        the second argument.

    ``use_sandboxes``: if this key equals ``True``, the program is executed
                     in the SupervisedExecutor, otherwise the UnsafeExecutor
                     is used

    ``inwer_time_limit``: time limit in ms
                        (optional, the default is 30 s)

    ``inwer_mem_limit``: memory limit in KiB
                        (optional, the default is 256 MiB)

    ``inwer_output_limit``: output limit in B
                        (optional, the default is 10 KiB)

    Returns a new environ, whose ``stdout`` key contains the program's
    output.

    The verifying program is expected to return 0, its first line of output
    should begin with "OK". If this does not happen, an appropriate message
    is logged.

    Program's output is returned under the ``stdout`` key. If the output has
    more than ``inwer_output_limit`` bytes and ``use_sandboxes`` is
    set to ``True``, the execution of the program fails with ``OLE`` result
    code.
    """

    use_sandboxes = environ.get('use_sandboxes', False)
    ft.download(environ, 'exe_file', 'inwer', skip_if_exists=True, add_to_cache=True)
    ft.download(environ, 'in_file', 'in', skip_if_exists=True, add_to_cache=True)
    os.chmod(tempcwd('inwer'), 0o500)

    renv = _run_inwer(environ, use_sandboxes)
    if renv['result_code'] != "OK":
        logger.error(
            "Inwer failed!\nEnviron dump: %s\nExecution environ: %s", environ, renv
        )
    elif not renv['stdout'][0].startswith(b"OK"):
        logger.error(
            "Bad inwer output!\nEnviron dump: %s\n" "Execution environ: %s",
            environ,
            renv,
        )

    return renv
