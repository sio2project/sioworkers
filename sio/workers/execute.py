import sys
import os
import subprocess
import tempfile
import signal
from threading import Timer
import logging

from sio.workers import util

logger = logging.getLogger(__name__)

class ExecError(RuntimeError):
    pass

class noquote(str):
    pass

def shellquote(s):
    if isinstance(s, noquote):
        return str(s)
    return "'" + s.replace("'", "'\\''") + "'"

def execute(command, env=None, split_lines=False, ignore_errors=False,
            extra_ignore_errors=(), stdin='', mem_limit=None,
            time_limit=None, real_time_limit=None, environ=None,
            environ_prefix=''):
    """
    Utility function to execute a command and return the output.

    ``command``
      The command to execute --- may be a list or a string. If this is a list,
      all the arguments will be shell-quoted unless wrapped in
      :class:`sio.workers.execute.nowrap`. If this is a string, it will be
      directly passed to :class:`subprocess.Popen` with ``shell=True``.

    ``env``
      The dictionary passed as environment. Non-string values are automatically
      converted to strings. If not present, the current process' environment is
      used. In all cases, the environment is augmented by adding ``LC_ALL`` and
      ``LANGUAGE`` set to ``en_US.UTF-8``.

    ``split_lines``
      If ``True``, the output from the called program is returned as a list of
      lines, otherwise just one big string.

    ``ignore_errors``
      Do not throw :exc:`ExecError` if the program exits with non-zero code.

    ``extra_ignore_errors``
      Do not throw :exc:`ExecError` if the program exits with one of the
      error codes in ``extra_ignore_errors``.

    ``stdin``
      Data to pass to the standard input of the program.

    ``mem_limit``
      Memory limit (``ulimit -v``), in MB.

    ``time_limit``
      CPU time limit (``ulimit -s``), in seconds.

    ``real_time_limit``
      Wall clock time limit, in seconds.

    ``environ``
      If present, this should be the ``environ`` dictionary. It's used to
      extract values for ``mem_limit``, ``time_limit`` and ``real_time_limit``
      from it.

    ``environ_prefix``
      Prefix for ``mem_limit``, ``time_limit`` and ``real_time_limit`` keys
      in ``environ``.

    The function return the tuple ``(retcode, output)`` where ``retcode`` is
    the program's return code and the output is program's stdout and stderr.
    """

    if isinstance(command, list):
        command = ' '.join(map(shellquote, command))

    if environ:
        mem_limit = environ.get(environ_prefix + 'mem_limit', mem_limit)
        time_limit = environ.get(environ_prefix + 'time_limit', time_limit)
        real_time_limit = environ.get(
                environ_prefix + 'real_time_limit', real_time_limit)

    if not env:
        env = os.environ.copy()

    if time_limit and real_time_limit is None:
        real_time_limit = 2 * time_limit

    env['LC_ALL'] = 'en_US.UTF-8'
    env['LANGUAGE'] = 'en_US.UTF-8'
    for key, value in env.iteritems():
        env[key] = str(value)

    # Using temporary file is way faster than using subproces.PIPE.
    o = tempfile.TemporaryFile()

    ulimit_args = []
    if mem_limit:
        command = 'ulimit -v %d && %s' % (mem_limit * 1024, command)
    if time_limit:
        command = 'ulimit -t %d && %s' % (time_limit, command)

    perf_timer = util.PerfTimer()

    p = subprocess.Popen(command,
                         stdin=subprocess.PIPE,
                         stdout=o,
                         stderr=subprocess.STDOUT,
                         shell=True,
                         close_fds=True,
                         universal_newlines=True,
                         env=env)
    p.stdin.write(stdin)
    p.stdin.close()

    kill_timer = None
    if real_time_limit:
        kill_timer = Timer(real_time_limit,
                lambda: os.kill(p.pid, signal.SIGKILL))
        kill_timer.start()
    rc = p.wait()
    if kill_timer:
        kill_timer.cancel()

    logger.debug('Command "%s" exited with code %d, took %.2fs',
            command, rc, perf_timer.elapsed)

    o.seek(0)
    data = o.read()
    if split_lines:
        data = data.split('\n')
    if rc and not ignore_errors and rc not in extra_ignore_errors:
        raise ExecError('Failed to execute command: %s\n%s' % (command, data))

    return rc, data

