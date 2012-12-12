import os
import subprocess
import tempfile
import signal
from threading import Timer
import logging

from sio.workers import util
from sio.workers.sandbox import get_sandbox, Sandbox
import traceback
from os import path
from sio.workers.util import ceil_ms2s, ms2s, s2ms
import re

logger = logging.getLogger(__name__)

class ExecError(RuntimeError):
    pass

class noquote(str):
    pass

def _argquote(s):
    if isinstance(s, noquote):
        return str(s)
    if isinstance(s, list):
        s = ' '.join(map(_argquote, s))
    return "'" + s.replace("'", "'\\''") + "'"

def shellquote(s):
    if isinstance(s, list):
        return " ".join(map(_argquote, s))
    else:
        return s

def ulimit(command, mem_limit=None, time_limit=None, **kwargs):
    # This could be nicely replaced with preexec_fn + resource.setrlimit, but
    # it does not work: RLIMIT_VMEM is usually not available (and we must take
    # into consideration that python has to fit in it before execve)
    command = isinstance(command, list) and command or [command]
    if mem_limit:
        command = ['ulimit', '-v', str(mem_limit), noquote('&&')] + command
        # Unlimited stack
        command = ['ulimit', '-Ss', 'unlimited', noquote('&&')] + command

    if time_limit:
        command = ['ulimit', '-t', str(ceil_ms2s(time_limit)),
                    noquote('&&')] + command

    return command

def execute_command(command, env=None, split_lines=False, stdin=None,
                    stdout=None, stderr=None, forward_stderr=False,
                    capture_output=False, output_limit=None,
                    real_time_limit=None,
                    ignore_errors=False, extra_ignore_errors=(), **kwargs):
    """ Utility function to run arbitrary command.
        ``stdin``
          Could be either file opened with ``open(fname, 'r')`` or None (inherited).

        ``stdout``, ``stderr``
          Could be files opened with ``open(fname, 'w')``, sys.std*
          or None - then it's suppressed.

        ``forward_stderr``
          Forwards stderr to stdin.

        ``capture_output``
          Returns program output in renv key ``stdout``.

        ``output_limit``
          Limits returned output when ``capture_output=True`` (in bytes).

        Returns renv: dictionary containing:
        ``realtime_used``
          Wall clock time it took to execute the command (in ms).

        ``return_code``
          Status code that program returned.

        ``stdout``
          Only when ``capture_output=True``: output of the command
    """
    # Using temporary file is way faster than using subproces.PIPE
    # and it prevents deadlocks. Also using stdin/stdout as file opened with
    # ``open`` has no performance penalty.
    command = shellquote(command)

    logger.debug('Executing: %s', command)

    stdout = capture_output and tempfile.TemporaryFile() or stdout
    # redirect output to /dev/null if None given
    devnull = open(os.devnull, 'wb')
    stdout = stdout or devnull
    stderr = stderr or devnull

    ret_env = {}
    if env is not None:
        for key, value in env.iteritems():
            env[key] = str(value)

    perf_timer = util.PerfTimer()
    p = subprocess.Popen(command,
                         stdin=stdin,
                         stdout=stdout,
                         stderr=forward_stderr and subprocess.STDOUT
                                                or stderr,
                         shell=True,
                         close_fds=True,
                         universal_newlines=True,
                         env=env)

    kill_timer = None
    if real_time_limit:
        kill_timer = Timer(ms2s(real_time_limit),
                lambda: os.kill(p.pid, signal.SIGKILL))
        kill_timer.start()

    rc = p.wait()
    ret_env['return_code'] = rc

    if kill_timer:
        kill_timer.cancel()

    ret_env['realtime_used'] = s2ms(perf_timer.elapsed)

    logger.debug('Command "%s" exited with code %d, took %.2fs',
            str(command), rc, perf_timer.elapsed)

    devnull.close()
    if capture_output:
        stdout.seek(0)
        ret_env['stdout'] = stdout.read(output_limit or -1)
        stdout.close()
        if split_lines:
            ret_env['stdout'] = ret_env['stdout'].split('\n')

    if rc and not ignore_errors and rc not in extra_ignore_errors:
        raise ExecError('Failed to execute command: %s. Returned with code %s\n'
                        % (command, rc))

    return ret_env

class BaseExecutor(object):
    """Base class for Executors: command environment managers.

        It's behavior depends on class instance, see it's docstring. Objects are
        callable context managers, so typical usage would be like:
            with executor_instance:
                executor_instance(command, kwargs...)

        Most of executors supports following options for ``__call__`` method:
        ``command``
          The command to execute --- may be a list or a string. If this is a list,
          all the arguments will be shell-quoted unless wrapped in
          :class:`sio.workers.executors.noquote`. If this is a string, it will be
          converted to ``noquote``ed one-element list.
          Command is passed to ``subprocess.Popen`` with ``shell=True``, but may
          be manipulated in various ways depending on concrete class.

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
          File object which should be redirected to standard input of the program.

        ``stdout``, ``stderr``
          Could be files opened with ``open(fname, 'w')``, sys.*
          or None - then it's suppressed (which is default).
          See also: ``capture_output``

        ``capture_output``
          Returns program output in return dict at key ``stdout``.

        ``output_limit``
          Limits returned output when ``capture_output=True`` (in bytes).

        ``mem_limit``
          Memory limit (``ulimit -v``), in KiB.

        ``time_limit``
          CPU time limit (``ulimit -s``), in miliseconds.

        ``real_time_limit``
          Wall clock time limit, in miliseconds.

        ``environ``
          If present, this should be the ``environ`` dictionary. It's used to
          extract values for ``mem_limit``, ``time_limit`` and ``real_time_limit``
          from it.

        ``environ_prefix``
          Prefix for ``mem_limit``, ``time_limit`` and ``real_time_limit`` keys
          in ``environ``.

        ``**kwargs``
          Other arguments handled by some executors. See their documentation.

        The method returns dictionary (called ``renv``) containing:
        ``realtime_used``
          Wall clock time it took to execute command (in ms).

        ``return_code``
          Status code that program returned.

        ``stdout``
          Only when ``capture_output=True``: output of command

        Some executors also returns other keys i.e:
        ``time_used``, ``result_code``, ``mem_used``, ``num_syscalls``
    """

    def __enter__(self):
        raise NotImplementedError('BaseExecutor is abstract!')

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def _execute(self, command, **kwargs):
        raise NotImplementedError('BaseExecutor is abstract!')

    def __call__(self, command, env=None, split_lines=False, ignore_errors=False,
                extra_ignore_errors=(), stdin=None, stdout=None, stderr=None,
                forward_stderr=False, capture_output=False,
                mem_limit=None, time_limit=None,
                real_time_limit=None, output_limit=None, environ={},
                environ_prefix='', **kwargs):
        if not isinstance(command, list):
            command = [noquote(command), ]

        if environ:
            mem_limit = environ.get(environ_prefix + 'mem_limit', mem_limit)
            time_limit = environ.get(environ_prefix + 'time_limit', time_limit)
            real_time_limit = environ.get(
                    environ_prefix + 'real_time_limit', real_time_limit)
            output_limit = environ.get(
                    environ_prefix + 'output_limit', output_limit)

        if not env:
            env = os.environ.copy()

        env['LC_ALL'] = 'en_US.UTF-8'
        env['LANGUAGE'] = 'en_US.UTF-8'

        return self._execute(command, env=env, split_lines=split_lines,
                ignore_errors=ignore_errors,
                extra_ignore_errors=extra_ignore_errors,
                stdin=stdin, stdout=stdout, stderr=stderr,
                mem_limit=mem_limit, time_limit=time_limit,
                real_time_limit=real_time_limit, output_limit=output_limit,
                forward_stderr=forward_stderr, capture_output=capture_output,
                environ=environ, environ_prefix=environ_prefix, **kwargs)


class UnprotectedExecutor(BaseExecutor):
    """Executes command in completely unprotected manner.

       Warning: time limiting is counted with accuracy of seconds.
    """

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def _execute(self, command, **kwargs):
        if kwargs['time_limit'] and kwargs['real_time_limit'] is None:
            kwargs['real_time_limit'] = 2 * kwargs['time_limit']

        command = ulimit(command, **kwargs)

        renv = execute_command(command, **kwargs)
        return renv


TIME_OUTPUT_RE = re.compile(r'^user\s+([0-9]+)m([0-9.]+)s$', re.MULTILINE)
class DetailedUnprotectedExecutor(UnprotectedExecutor):
    """This executor returns extended process status (over UnprotectedExecutor.)

    It reserves process stderr for time counting, so ``stderr`` arg is ignored.
    It adds following keys to ``renv``:
      ``time_used``: Linux user-time used by process
      ``result_code``: TLE, OK, RE.
      ``result_string``: string describing ``result_code``
    """

    def _execute(self, command, **kwargs):
        command = ['bash', '-c', [noquote('time')] + command]
        stderr = tempfile.TemporaryFile()
        kwargs['stderr'] = stderr
        kwargs['forward_stderr'] = False
        renv = super(DetailedUnprotectedExecutor, self)._execute(command,
                                                                    **kwargs)
        stderr.seek(0)
        output = stderr.read()
        stderr.close()
        time_output_matches = TIME_OUTPUT_RE.findall(output)
        if time_output_matches:
            mins, secs = time_output_matches[-1]
            renv['time_used'] = int((int(mins) * 60 + float(secs)) * 1000)
        else:
            raise RuntimeError('Could not find output of time program. '
                'Captured output: %s' % output)

        if kwargs['time_limit'] is not None \
                and renv['time_used'] >= 0.99 * kwargs['time_limit']:
            renv['result_string'] = 'time limit exceeded'
            renv['result_code'] = 'TLE'
        elif renv['return_code'] == 0:
            renv['result_string'] = 'ok'
            renv['result_code'] = 'OK'
        else:
            renv['result_string'] = 'program exited with code %d' \
                                                        % renv['return_code']
            renv['result_code'] = 'RE'

        renv['mem_used'] = 0
        renv['num_syscalls'] = 0

        return renv


class SandboxExecutor(UnprotectedExecutor):
    """SandboxedExecutor is intended to run programs delivered in sandbox package.

       In addition to :class:BaseExecutor it handles following options in __call__:
         ``use_path`` If false (default) and first argument of command is relative
                      then its prepended with sandbox path.

       .. note:: Sandbox does not mean isolation, it's just part of filesytem.
    """

    def __enter__(self):
        self.sandbox.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.sandbox.__exit__(exc_type, exc_value, traceback)

    def _get_sandbox(self, name):
            return isinstance(name, Sandbox) and name or get_sandbox(name)

    def __init__(self, sandbox):
        """``sandbox`` can be either a :class:`Sandbox` instance or a sandbox name."""
        self.sandbox = self._get_sandbox(sandbox)

    def __str__(self):
        return 'SandboxExecutor(%s)' % (self.sandbox,)

    @property
    def rpath(self):
        """Returns path to sandbox root as visible during command execution."""
        return self.sandbox.path

    @property
    def path(self):
        """Returns real, absolute path to sandbox root."""
        return self.sandbox.path

    def _env_paths(self, suffix):
        return "%s:%s" % (path.join(self.path, suffix),
                            path.join(self.path, 'usr', suffix))

    def _execute(self, command, **kwargs):
        if not kwargs.get('use_path', False) and command[0][0] != '/':
            command[0] = os.path.join(self.path, command[0])

        env = kwargs.get('env')
        env['PATH'] = '%s:%s' % (self._env_paths('bin'), env['PATH'])

        if not self.sandbox.has_fixup('elf_loader_patch'):
            env['LD_LIBRARY_PATH'] = self._env_paths('lib')

        return super(SandboxExecutor, self)._execute(command, **kwargs)


class _SIOSupervisedExecutor(SandboxExecutor):
    _supervisor_codes = {
            0: 'OK',
            120: 'OLE',
            121: 'RV',
            124: 'MLE',
            125: 'TLE'
        }

    def __init__(self, sandbox_name):
        super(_SIOSupervisedExecutor, self).__init__(sandbox_name)

    def _supervisor_result_to_code(self, result):
        return self._supervisor_codes.get(int(result), 'RE')

    def _execute(self, command, **kwargs):
        env = kwargs.get('env')
        environ = kwargs['environ']
        env.update({
                    'MEM_LIMIT': kwargs['mem_limit'] or 64 << 10,
                    'TIME_LIMIT': kwargs['time_limit'] or 30000,
                    'OUT_LIMIT': kwargs['output_limit'] or 50 << 20,
                    })

        if kwargs['time_limit'] and kwargs['real_time_limit'] is None:
            env['HARD_LIMIT'] = 64 * kwargs['real_time_limit']
            # Limiting outside supervisor
            kwargs['real_time_limit'] = 1 + 2 * env['HARD_LIMIT']


        renv = {}
        try:
            result_file = tempfile.NamedTemporaryFile(dir=os.getcwd())
            kwargs['ignore_errors'] = True
            renv = execute_command(
                        command + [noquote('3>'), result_file.name],
                         **kwargs
                        )
            # TODO: supervisor errors handling (for example hard hard TLE)

            if renv['return_code']:
                raise ExecError('Supervisor returned code %s'
                                % renv['return_code'])


            result_file.seek(0)
            status_line = result_file.readline().strip().split()[1:]
            renv['result_string'] = result_file.readline().strip()
            result_file.close()
            for num, key in enumerate(('result_code', 'time_used',
                        None, 'mem_used', 'num_syscalls')):
                    if key:
                        renv[key] = int(status_line[num])

            result_code = self._supervisor_result_to_code(
                                                        renv['result_code'])
        except Exception, e:
            logger.error('SupervisedExecutor error: %s', traceback.format_exc())
            logger.error('SupervisedExecutor error dirlist: %s: %s',
                         os.getcwd(), str(os.listdir('.')))

            result_code = 'SE'
            for i in ('time_used', 'mem_used', 'num_syscalls'):
                renv.setdefault(i, 0)
            renv['result_string'] = str(e)

        renv['result_code'] = result_code

        return renv


class VCPUExecutor(_SIOSupervisedExecutor):
    """Runs program in controlled environment while counting CPU instructions.

       Executed programs may only use stdin/stdout/stderr and manage it's
       own memory. Retuns extended statistics in renv.
    """

    def __init__(self):
        super(VCPUExecutor, self).__init__('vcpu_exec-sandbox')

    def _execute(self, command, **kwargs):
        command = [os.path.join(self.sandbox.path, 'pin-supervisor',
                                         'supervisor-bin', 'supervisor'),
                    '-f', '3', '--'] + command
        return super(VCPUExecutor, self)._execute(command, **kwargs)


class SupervisedExecutor(_SIOSupervisedExecutor):
    """Executes program in supervised mode.

       Executed programs may only use stdin/stdout/stderr and manage it's
       own memory. Retuns extended statistics in renv.
    """

    def __init__(self):
        super(SupervisedExecutor, self).__init__('exec-sandbox')

    def _execute(self, command, **kwargs):
        command = [os.path.join(self.sandbox.path, 'bin', 'supervisor'),
                    '-f', '3'   ] + command
        return super(SupervisedExecutor, self)._execute(command, **kwargs)
