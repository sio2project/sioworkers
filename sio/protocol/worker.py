from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet import threads
from sio.workers import runner
from sio.protocol import rpc


class WorkerProtocol(rpc.WorkerRPC):
    def __init__(self):
        rpc.WorkerRPC.__init__(self, server=False)

    def cmd_run(self, env):
        d = threads.deferToThread(runner.run, env)
        return d


class WorkerFactory(ReconnectingClientFactory):
    protocol = WorkerProtocol
