from __future__ import absolute_import
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet import threads
from sio.workers import runner
from sio.protocol import rpc
import platform
from twisted.logger import Logger, LogLevel
import six

log = Logger()

# ingen replaces the environment, so merge it
def _runner_wrap(env):
    renv = runner.run(env)
    env.update(renv)
    return env


class WorkerProtocol(rpc.WorkerRPC):
    def __init__(self):
        rpc.WorkerRPC.__init__(self, server=False)
        self.running = {}

    def getHelloData(self):
        return {
            'name': self.factory.name,
            'concurrency': self.factory.concurrency,
            'available_ram_mb': self.factory.available_ram_mb,
            'can_run_cpu_exec': self.factory.can_run_cpu_exec,
        }

    def cmd_run(self, env):
        job_type = env['job_type']
        if job_type == 'cpu-exec':
            if self.running:
                raise RuntimeError('Send cpu-exec job to busy worker')
            if not self.factory.can_run_cpu_exec:
                raise RuntimeError('Send cpu-exec job to worker which can\'t run it')
        if any(
            [(task['job_type'] == 'cpu-exec') for task in six.itervalues(self.running)]
        ):
            raise RuntimeError('Send job to worker already running cpu-exec job')
        task_id = env['task_id']
        log.info('running {job_type} {tid}', job_type=job_type, tid=task_id)
        self.running[task_id] = env
        d = threads.deferToThread(_runner_wrap, env)

        # Log errors, but pass them to sioworkersd anyway
        def _error(x):
            log.failure('Error during task execution:', x, LogLevel.warn)
            return x

        def _done(x):
            del self.running[task_id]
            log.info('{tid} done.', tid=task_id)
            return x

        d.addBoth(_done)
        d.addErrback(_error)
        return d

    def cmd_get_running(self):
        # sets are not json-serializable
        return list(self.running.keys())


class WorkerFactory(ReconnectingClientFactory):
    maxDelay = 60
    protocol = WorkerProtocol

    def __init__(
        self, concurrency=1, available_ram_mb=1024, can_run_cpu_exec=False, name=None
    ):
        self.concurrency = concurrency
        self.available_ram_mb = available_ram_mb
        self.can_run_cpu_exec = can_run_cpu_exec
        if name is None:
            self.name = platform.node()
        else:
            self.name = name
