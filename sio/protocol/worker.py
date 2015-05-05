from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet import threads
from sio.workers import runner
from sio.protocol import rpc
import platform


class WorkerProtocol(rpc.WorkerRPC):
    def __init__(self):
        rpc.WorkerRPC.__init__(self, server=False)
        self.running = {}

    def getHelloData(self):
        # concurrency should be passed from command line,
        # but runner currently isn't thread-safe, so for now return 1
        return {'name': platform.node(),
                'concurrency': 1}   # TODO

    def cmd_run(self, env):
        if (env.get('exclusive', True) and self.running) or \
                any(i.get('exclusive', True) for i in
                self.running.itervalues()):
            raise AssertionError('Multiple tasks on exclusive worker')
        task_id = env['task_id']
        print 'running', task_id
        self.running[task_id] = env
        d = threads.deferToThread(runner.run, env)

        # Log errors, but pass them to sioworkersd anyway
        def _error(x):
            print 'Error during task execution:', x
            return x

        def _done(x):
            del self.running[task_id]
            print task_id, 'done.'
            return x
        d.addBoth(_done)
        d.addErrback(_error)
        return d

    def cmd_get_running(self):
        return self.running.keys()


class WorkerFactory(ReconnectingClientFactory):
    protocol = WorkerProtocol
