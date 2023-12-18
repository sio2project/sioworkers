from __future__ import absolute_import, division
import os
import subprocess
import tempfile
import signal
from threading import Timer
import logging
import re
import sys
import traceback
from os import path

from sio.workers import util, elf_loader_patch
from sio.workers.sandbox import get_sandbox
from sio.workers.util import (
    ceil_ms2s,
    decode_fields,
    ms2s,
    s2ms,
    path_join_abs,
    null_ctx_manager,
    tempcwd,
)
import six
from six.moves import map

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
        command = ['ulimit', '-t', str(ceil_ms2s(time_limit)), noquote('&&')] + command

    return command


def execute_command(
    command,
    env=None,
    split_lines=False,
    stdin=None,
    stdout=None,
    stderr=None,
    forward_stderr=False,
    capture_output=False,
    output_limit=None,
    real_time_limit=None,
    ignore_errors=False,
    extra_ignore_errors=(),
    pass_fds=(),
    **kwargs
):
    """Utility function to run arbitrary command.
    ``stdin``
      Could be either file opened with ``open(fname, 'r')``
      or None (then it is inherited from current process).

    ``stdout``, ``stderr``
      Could be files opened with ``open(fname, 'w')``, sys.std*
      or None - then it's suppressed.

    ``forward_stderr``
      Forwards stderr to stdout.

    ``capture_output``
      Returns program output in renv key ``stdout``.

    ``output_limit``
      Limits returned output when ``capture_output=True`` (in bytes).

    Returns renv: dictionary containing:
    ``real_time_used``
      Wall clock time it took to execute the command (in ms).

    ``return_code``
      Status code that program returned.

    ``real_time_killed``
      Only when process was killed due to exceeding real time limit.

    ``stdout``
      Only when ``capture_output=True``: output of the command

    ``pass_fds``
      Extra file descriptors to pass to the command.
    """
    # Using temporary file is way faster than using subproces.PIPE
    # and it prevents deadlocks.
    command = shellquote(command)

    logger.debug('Executing: %s', command)

    stdout = capture_output and tempfile.TemporaryFile() or stdout
    # redirect output to /dev/null if None given
    devnull = open(os.devnull, 'wb')
    stdout = stdout or devnull
    stderr = stderr or devnull

    ret_env = {}
    if env is not None:
        for key, value in six.iteritems(env):
            env[key] = str(value)

    perf_timer = util.PerfTimer()
    p = subprocess.Popen(
        command,
        stdin=stdin,
        stdout=stdout,
        stderr=forward_stderr and subprocess.STDOUT or stderr,
        shell=True,
        close_fds=True,
        universal_newlines=True,
        env=env,
        cwd=tempcwd(),
        preexec_fn=os.setpgrp,
        pass_fds=pass_fds,
    )

    kill_timer = None
    if real_time_limit:

        def oot_killer():
            ret_env['real_time_killed'] = True
            os.killpg(p.pid, signal.SIGKILL)

        kill_timer = Timer(ms2s(real_time_limit), oot_killer)
        kill_timer.start()

    rc = p.wait()
    ret_env['return_code'] = rc

    if kill_timer:
        kill_timer.cancel()

    ret_env['real_time_used'] = s2ms(perf_timer.elapsed)

    logger.debug(
        'Command "%s" exited with code %d, took %.2fs',
        str(command),
        rc,
        perf_timer.elapsed,
    )

    devnull.close()
    if capture_output:
        stdout.seek(0)
        ret_env['stdout'] = stdout.read(output_limit or -1)
        stdout.close()
        if split_lines:
            ret_env['stdout'] = ret_env['stdout'].split(b'\n')

    if rc and not ignore_errors and rc not in extra_ignore_errors:
        raise ExecError(
            'Failed to execute command: %s. Returned with code %s\n' % (command, rc)
        )

    return ret_env


class BaseExecutor(object):
    """Base class for Executors: command environment managers.

    Its behavior depends on class instance, see its docstring. Objects are
    callable context managers, so typical usage would be like::

        with executor_instance:
            executor_instance(command, kwargs...)

    Most of executors support following options for ``__call__`` method:

    ``command``
      The command to execute --- may be a list or a string. If this is a
      list, all the arguments will be shell-quoted unless wrapped in
      :class:`sio.workers.executors.noquote`. If this is a string, it will
      be converted to ``noquote``-ed one-element list.
      Command is passed to ``subprocess.Popen`` with ``shell=True``, but may
      be manipulated in various ways depending on concrete class.

    ``env``
      The dictionary passed as environment. Non-string values are
      automatically converted to strings. If not present, the current
      process' environment is used. In all cases, the environment
      is augmented by adding ``LC_ALL`` and ``LANGUAGE`` set
      to ``en_US.UTF-8``.

    ``ignore_errors``
      Do not throw :exc:`ExecError` if the program exits with error

    ``extra_ignore_errors``
      Do not throw :exc:`ExecError` if the program exits with one of the
      error codes in ``extra_ignore_errors``.

    ``stdin``
      File object which should be redirected to standard input of
      the program.

    ``stdout``, ``stderr``
      Could be files opened with ``open(fname, 'w')``, sys.*
      or None - then it's suppressed (which is default).
      See also: ``capture_output``

    ``capture_output``
      Returns program output in ``stdout`` key of ``renv``.

    ``split_lines``
      If ``True``, the output from the called program is returned as a list
      of lines, otherwise just one big string.

    ``forward_stderr``
      Forwards ``stderr`` to ``stdout``.

    ``output_limit``
      Limits amount of data program can write to stdout, in KiB.

    ``mem_limit``
      Memory limit (``ulimit -v``), in KiB.

    ``time_limit``
      CPU time limit (``ulimit -t``), in miliseconds.

    ``real_time_limit``
      Wall clock time limit, in miliseconds.

    ``environ``
      If present, this should be the ``environ`` dictionary. It's used to
      extract values for ``mem_limit``, ``time_limit``, ``real_time_limit``
      and ``output_limit`` from it.

    ``environ_prefix``
      Prefix for ``mem_limit``, ``time_limit``, ``real_time_limit`` and
      ``output_limit`` keys in ``environ``.

    ``**kwargs``
      Other arguments handled by some executors. See their documentation.

    The method returns dictionary (called ``renv``) containing:

    ``real_time_used``
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

    def __call__(
        self,
        command,
        env=None,
        split_lines=False,
        ignore_errors=False,
        extra_ignore_errors=(),
        stdin=None,
        stdout=None,
        stderr=None,
        forward_stderr=False,
        capture_output=False,
        mem_limit=None,
        time_limit=None,
        real_time_limit=None,
        output_limit=None,
        environ={},
        environ_prefix='',
        **kwargs
    ):
        if not isinstance(command, list):
            command = [
                noquote(command),
            ]

        if environ:
            mem_limit = environ.get(environ_prefix + 'mem_limit', mem_limit)
            time_limit = environ.get(environ_prefix + 'time_limit', time_limit)
            real_time_limit = environ.get(
                environ_prefix + 'real_time_limit', real_time_limit
            )
            output_limit = environ.get(environ_prefix + 'output_limit', output_limit)

        if not env:
            env = os.environ.copy()

        env['LC_ALL'] = 'en_US.UTF-8'
        env['LANGUAGE'] = 'en_US.UTF-8'

        return self._execute(
            command,
            env=env,
            split_lines=split_lines,
            ignore_errors=ignore_errors,
            extra_ignore_errors=extra_ignore_errors,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            mem_limit=mem_limit,
            time_limit=time_limit,
            real_time_limit=real_time_limit,
            output_limit=output_limit,
            forward_stderr=forward_stderr,
            capture_output=capture_output,
            environ=environ,
            environ_prefix=environ_prefix,
            **kwargs
        )


class UnprotectedExecutor(BaseExecutor):
    """Executes command in completely unprotected manner.

    .. note:: time limiting is counted with accuracy of seconds.
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

    .. note:: It reserves process stderr for time counting, so ``stderr``
              arg is ignored.

    This class adds the following keys to ``renv``:

      ``time_used``: Linux user-time used by process

      ``result_code``: TLE, OK, RE.

      ``result_string``: string describing ``result_code``
    """

    def _execute(self, command, **kwargs):
        command = ['bash', '-c', [noquote('time')] + command]
        stderr = tempfile.TemporaryFile()
        kwargs['stderr'] = stderr
        kwargs['forward_stderr'] = False
        renv = super(DetailedUnprotectedExecutor, self)._execute(command, **kwargs)
        stderr.seek(0)
        output = stderr.read()
        stderr.close()
        time_output_matches = TIME_OUTPUT_RE.findall(output.decode())
        if time_output_matches:
            mins, secs = time_output_matches[-1]
            renv['time_used'] = int((int(mins) * 60 + float(secs)) * 1000)
        elif 'real_time_killed' in renv:
            renv['time_used'] = renv['real_time_used']
        else:
            raise RuntimeError(
                'Could not find output of time program. ' 'Captured output: %s' % output
            )

        if (
            kwargs['time_limit'] is not None
            and renv['time_used'] >= 0.95 * kwargs['time_limit']
        ):
            renv['result_string'] = 'time limit exceeded'
            renv['result_code'] = 'TLE'
        elif 'real_time_killed' in renv:
            renv['result_string'] = 'real time limit exceeded'
            renv['result_code'] = 'TLE'
        elif renv['return_code'] == 0:
            renv['result_string'] = 'ok'
            renv['result_code'] = 'OK'
        elif renv['return_code'] > 128:  # os.WIFSIGNALED(1) returns True
            renv['result_string'] = 'program exited due to signal %d' % os.WTERMSIG(
                renv['return_code']
            )
            renv['result_code'] = 'RE'
        else:
            renv['result_string'] = 'program exited with code %d' % renv['return_code']
            renv['result_code'] = 'RE'

        renv['mem_used'] = 0
        renv['num_syscalls'] = 0

        return renv


class SandboxExecutor(UnprotectedExecutor):
    """SandboxedExecutor is intended to run programs delivered in ``sandbox`` package.

    This executor accepts following extra arguments in ``__call__``:
       ``use_path`` If false (default) and first argument of command is
                    relative then it's prepended with sandbox path.

     .. note:: Sandbox does not mean isolation, it's just part of filesytem.

     ..
    """

    def __enter__(self):
        self.sandbox.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.sandbox.__exit__(exc_type, exc_value, traceback)

    def __init__(self, sandbox):
        """``sandbox`` has to be a sandbox name."""
        self.sandbox = get_sandbox(sandbox)

    def __str__(self):
        return 'SandboxExecutor(%s)' % (self.sandbox,)

    @property
    def rpath(self):
        """Contains path to sandbox root as visible during command execution."""
        return self.sandbox.path

    @property
    def path(self):
        """Contains real, absolute path to sandbox root."""
        return self.sandbox.path

    def _env_paths(self, suffix):
        return "%s:%s" % (
            path.join(self.path, suffix),
            path.join(self.path, 'usr', suffix),
        )

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
        125: 'TLE',
    }

    def __init__(self, sandbox_name):
        super(_SIOSupervisedExecutor, self).__init__(sandbox_name)

    def _supervisor_result_to_code(self, result):
        return self._supervisor_codes.get(int(result), 'RE')

    @decode_fields(['result_string'])
    def _execute(self, command, **kwargs):
        env = kwargs.get('env')
        env.update(
            {
                'MEM_LIMIT': kwargs['mem_limit'] or 64 * 2 ** 10,
                'TIME_LIMIT': kwargs['time_limit'] or 30000,
                'OUT_LIMIT': kwargs['output_limit'] or 50 * 2 ** 20,
            }
        )

        if kwargs['real_time_limit']:
            env['HARD_LIMIT'] = 1 + ceil_ms2s(kwargs['real_time_limit'])
        elif kwargs['time_limit'] and kwargs['real_time_limit'] is None:
            env['HARD_LIMIT'] = 1 + ceil_ms2s(64 * kwargs['time_limit'])

        if 'HARD_LIMIT' in env:
            # Limiting outside supervisor
            kwargs['real_time_limit'] = 2 * s2ms(env['HARD_LIMIT'])

        ignore_errors = kwargs.pop('ignore_errors')
        extra_ignore_errors = kwargs.pop('extra_ignore_errors')
        renv = {}
        try:
            result_file = tempfile.NamedTemporaryFile(dir=tempcwd())
            kwargs['ignore_errors'] = True
            renv = execute_command(
                command + [noquote('3>'), result_file.name], **kwargs
            )

            if 'real_time_killed' in renv:
                raise ExecError('Supervisor exceeded realtime limit')
            elif renv['return_code'] and renv['return_code'] not in extra_ignore_errors:
                raise ExecError('Supervisor returned code %s' % renv['return_code'])

            result_file.seek(0)
            status_line = result_file.readline().strip().split()[1:]
            renv['result_string'] = result_file.readline().strip()
            result_file.close()
            for num, key in enumerate(
                ('result_code', 'time_used', None, 'mem_used', 'num_syscalls')
            ):
                if key:
                    renv[key] = int(status_line[num])

            result_code = self._supervisor_result_to_code(renv['result_code'])

        except Exception as e:
            logger.error('SupervisedExecutor error: %s', traceback.format_exc())
            logger.error(
                'SupervisedExecutor error dirlist: %s: %s',
                tempcwd(),
                str(os.listdir(tempcwd())),
            )

            result_code = 'SE'
            for i in ('time_used', 'mem_used', 'num_syscalls'):
                renv.setdefault(i, 0)
            renv['result_string'] = str(e)

        renv['result_code'] = result_code

        if (
            result_code != 'OK'
            and not ignore_errors
            and not (result_code != 'RV' and renv['return_code'] in extra_ignore_errors)
        ):
            raise ExecError(
                'Failed to execute command: %s. Reason: %s'
                % (command, renv['result_string'])
            )
        return renv


class Sio2JailExecutor(SandboxExecutor):
    """Runs program in controlled environment while counting CPU instructions
    using Sio2Jail.

    Returns extended statistics in ``renv`` containing:

    ``time_used``: virtual time based on instruction counting (in ms).

    ``mem_used``: memory used (in KiB).

    ``result_code``: short code reporting result of rule obeying. Is one of
                     ``OK``, ``RE``, ``TLE``, ``MLE``, ``RV``

    ``result_string``: string describing ``result_code``
    """

    DEFAULT_MEMORY_LIMIT = 64 * 2 ** 10  # (in KiB)
    DEFAULT_OUTPUT_LIMIT = 50 * 2 ** 10  # (in KiB)
    DEFAULT_TIME_LIMIT = 30000  # (default virtual time limit in ms)
    INSTRUCTIONS_PER_VIRTUAL_SECOND = 2 * 10 ** 9
    REAL_TIME_LIMIT_MULTIPLIER = 16
    REAL_TIME_LIMIT_ADDEND = 1000  # (in ms)

    def __init__(self):
        super(Sio2JailExecutor, self).__init__('sio2jail_exec-sandbox-1.4.4')

    def _execute(self, command, **kwargs):
        options = []
        options += ['-b', os.path.join(self.rpath, 'boxes/minimal') + ':/:ro']
        options += [
            '--memory-limit',
            str(kwargs['mem_limit'] or self.DEFAULT_MEMORY_LIMIT) + 'K',
        ]
        options += [
            '--instruction-count-limit',
            str(
                (kwargs['time_limit'] or self.DEFAULT_TIME_LIMIT)
                * self.INSTRUCTIONS_PER_VIRTUAL_SECOND
                // 1000
            ),
        ]
        options += [
            '--rtimelimit',
            str(
                (kwargs['time_limit'] or self.DEFAULT_TIME_LIMIT)
                * self.REAL_TIME_LIMIT_MULTIPLIER
                + self.REAL_TIME_LIMIT_ADDEND
            )
            + 'ms',
        ]
        options += [
            '--output-limit',
            str(kwargs['output_limit'] or self.DEFAULT_OUTPUT_LIMIT) + 'K',
        ]
        command = [os.path.join(self.rpath, 'sio2jail')] + options + ['--'] + command

        renv = {}
        try:
            result_file = tempfile.NamedTemporaryFile(dir=tempcwd())
            kwargs['ignore_errors'] = True
            print(command)
            renv = execute_command(
                command + [noquote('2>'), result_file.name], **kwargs
            )

            if renv['return_code'] != 0:
                raise ExecError(
                    'Sio2Jail returned code %s, stderr: %s'
                    % (renv['return_code'], six.ensure_text(result_file.read(10240)))
                )

            result_file.seek(0)
            status_line = six.ensure_text(result_file.readline()).strip().split()[1:]
            renv['result_string'] = six.ensure_text(result_file.readline()).strip()
            result_file.close()
            for num, key in enumerate(
                ('result_code', 'time_used', None, 'mem_used', None)
            ):
                if key:
                    renv[key] = int(status_line[num])

            if renv['result_string'] == 'ok':
                renv['result_code'] = 'OK'
            elif renv['result_string'] == 'time limit exceeded':
                renv['result_code'] = 'TLE'
            elif renv['result_string'] == 'real time limit exceeded':
                renv['result_code'] = 'TLE'
            elif renv['result_string'] == 'memory limit exceeded':
                renv['result_code'] = 'MLE'
            elif renv['result_string'] == 'output limit exceeded':
                renv['result_code'] = 'OLE'
            elif renv['result_string'].startswith('intercepted forbidden syscall'):
                renv['result_code'] = 'RV'
            elif renv['result_string'].startswith('process exited due to signal'):
                renv['result_code'] = 'RE'
            else:
                raise ExecError(
                    'Unrecognized Sio2Jail result string: %s' % renv['result_string']
                )

        except (EnvironmentError, EOFError, RuntimeError) as e:
            logger.error('Sio2JailExecutor error: %s', traceback.format_exc())
            logger.error(
                'Sio2JailExecutor error dirlist: %s: %s',
                tempcwd(),
                str(os.listdir(tempcwd())),
            )

            renv['result_code'] = 'SE'
            for i in ('time_used', 'mem_used'):
                renv.setdefault(i, 0)
            renv['result_string'] = str(e)

            if not kwargs.get('ignore_errors', False):
                raise ExecError(
                    'Failed to execute command: %s. Reason: %s'
                    % (command, renv['result_string'])
                )

        return renv


class SupervisedExecutor(_SIOSupervisedExecutor):
    """Executes program in supervised mode.

       Sandboxing limitations may be controlled by passing following arguments
       to constructor:

         ``allow_local_open`` Allow opening files within current directory in \
                              read-only mode

         ``use_program_return_code`` Makes supervisor pass the program return \
                                     code to renv['return_code'] rather than \
                                     the sandbox return code.

       Following new arguments are recognized in ``__call__``:

          ``ignore_return`` Do not treat non-zero return code as runtime error.

          ``java_sandbox`` Sandbox name with JRE.

       Executed programs may only use stdin/stdout/stderr and manage it's
       own memory. Returns extended statistics in ``renv`` containing:

       ``time_used``: processor user time (in ms).

       ``mem_used``: memory used (in KiB).

       ``num_syscall``: number of times a syscall has been called

       ``result_code``: short code reporting result of rule obeying. Is one of \
                        ``OK``, ``RE``, ``TLE``, ``OLE``, ``MLE``, ``RV``

       ``result_string``: string describing ``result_code``
    """

    def __init__(self, allow_local_open=False, use_program_return_code=False, **kwargs):
        self.options = ['-q', '-f', '3']
        if allow_local_open:
            self.options += ['-l']
        if use_program_return_code:
            self.options += ['-r']
        super(SupervisedExecutor, self).__init__('exec-sandbox', **kwargs)

    def _execute(self, command, **kwargs):
        options = self.options
        if kwargs.get('ignore_return', False):
            options = options + ['-R']

        if kwargs.get('java_sandbox', ''):
            java = get_sandbox(kwargs['java_sandbox'])
            options = options + ['-j', os.path.join(java.path, 'usr', 'bin', 'java')]
        else:
            # Null context-manager
            java = null_ctx_manager()

        command = [os.path.join(self.rpath, 'bin', 'supervisor')] + options + command
        with java:
            return super(SupervisedExecutor, self)._execute(command, **kwargs)


class PRootExecutor(BaseExecutor):
    """PRootExecutor executor mimics ``chroot`` with ``mount --bind``.

    During execution ``sandbox.path`` becomes new ``/``.
    Current working directory is visible as itself and ``/tmp``.
    Also ``sandbox.path`` remains accessible under ``sandbox.path``.

    If *sandbox* doesn't contain ``/bin/sh`` or ``/lib``,
    then some basic is bound from *proot sandbox*.

    For more information about PRoot see http://proot.me.

    PRootExecutor adds support of following arguments in ``__call__``:

      ``proot_options`` Options passed to *proot* binary after those
                        automatically generated.
    """

    def __init__(self, sandbox):
        """``sandbox`` has to be a sandbox name."""
        self.chroot = get_sandbox(sandbox)
        self.proot = SandboxExecutor('proot-sandbox_amd64')

        self.options = []
        with self.chroot:
            with self.proot:
                self._proot_options()

    def __enter__(self):
        self.proot.__enter__()
        try:
            self.chroot.__enter__()
        except:
            self.proot.__exit__(*sys.exc_info())
            raise

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        exc = (exc_type, exc_value, traceback)
        try:
            self.chroot.__exit__(*exc)
            exc = (None, None, None)
        except:
            exc = sys.exc_info()
        finally:
            self.proot.__exit__(*exc)

    def _bind(self, what, where=None, force=False):
        if where is None:
            where = what

        where = path_join_abs(self.rpath, where)
        if not path.exists(what):
            raise RuntimeError("Binding not existing location")

        if force or not path.exists(path_join_abs(self.chroot.path, where)):
            self.options += ['-b', '%s:%s' % (what, where)]
            return True
        return False

    def _chroot(self, where):
        self.options += ['-r', where]

    def _pwd(self, pwd):
        """Sets new process initial pwd"""
        self.options += ['-w', path_join_abs(self.rpath, pwd)]

    def _verbosity(self, level):
        """-1: suppress, 0: warnings, 1: infos, 2: debug"""
        self.options += ['-v', str(level)]

    def _proot_options(self):
        self._verbosity(-1)
        self._chroot(self.chroot.path)

        sh_target = path.join(os.sep, 'bin', 'sh')
        if not path.exists(path_join_abs(self.chroot.path, sh_target)):
            self._bind(path_join_abs(self.proot.path, sh_target), sh_target)
        else:
            # If /bin/sh exists, then bind unpatched version to it
            sh_patched = elf_loader_patch._get_unpatched_name(
                path.realpath(path_join_abs(self.chroot.path, sh_target))
            )
            if path.exists(sh_patched):
                self._bind(sh_patched, sh_target, force=True)

        self._bind(os.path.join(self.proot.path, 'lib'), 'lib')
        self._bind(tempcwd(), 'tmp', force=True)

        # Make absolute `outside paths' visible in sandbox
        self._bind(self.chroot.path, force=True)
        self._bind(tempcwd(), force=True)

    def _execute(self, command, **kwargs):
        if kwargs['time_limit'] and kwargs['real_time_limit'] is None:
            kwargs['real_time_limit'] = 3 * kwargs['time_limit']

        options = self.options + kwargs.pop('proot_options', [])
        command = (
            [path.join('proot', 'proot')]
            + options
            + [path.join(self.rpath, 'bin', 'sh'), '-c', command]
        )

        return self.proot._execute(command, **kwargs)

    @property
    def rpath(self):
        """Contains path to sandbox root as visible during command execution."""
        return path.sep

    @property
    def path(self):
        """Contains real, absolute path to sandbox root."""
        return self.chroot.path
