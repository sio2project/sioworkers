from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet import threads
from sio.workers import runner
from sio.protocol import rpc
import platform
from twisted.logger import Logger, LogLevel

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
        return {'name': self.factory.name,
                'concurrency': self.factory.concurrency}

    def cmd_run(self, env):
        job_type = env['job_type']
        if job_type == 'cpu-exec' and self.running:
            raise AssertionError('Send cpu-exec job to busy worker')
        if any([(task['job_type'] == 'cpu-exec')
                for task in self.running.itervalues()]):
            raise AssertionError(
                    'Send job to worker already running cpu-exec job')
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

    def __init__(self, concurrency=1, name=None):
        self.concurrency = concurrency
        if name is None:
            self.name = platform.node()
        else:
            self.name = name
