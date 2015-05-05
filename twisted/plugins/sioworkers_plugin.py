import urlparse
from zope.interface import implements

from twisted.python import usage
from twisted.plugin import IPlugin
from twisted.application import service
from twisted.application import internet

from sio.protocol.worker import WorkerFactory
from filetracker.servers.run import DEFAULT_PORT as DEFAULT_FILETRACKER_PORT
import os
from sio.sioworkersd.manager import WorkerManager
from sio.sioworkersd.taskmanager import TaskManager
from sio.sioworkersd.db import DBWrapper
from sio.sioworkersd import siorpc

from sio.sioworkersd.fifo import FIFOScheduler


def _host_from_url(url):
    return urlparse.urlparse(url).hostname


class WorkerOptions(usage.Options):
    optParameters = [['port', 'p', 7888, "sioworkersd port number"]]
    optFlags = [
            ['local-filetracker', 'l',
                "Do not set FILETRACKER_URL automatically."]]

    def parseArgs(self, host):
        self['host'] = host


class WorkerServiceMaker(object):
    """Run worker process.
    """
    implements(service.IServiceMaker, IPlugin)
    tapname = 'worker'
    description = 'sio worker process'
    options = WorkerOptions

    def makeService(self, options):
        if not options['local-filetracker']:
            if 'FILETRACKER_URL' not in os.environ:
                default_filetracker_host = None
                if not default_filetracker_host:
                    default_filetracker_host = options['host']
                os.environ['FILETRACKER_URL'] = 'http://%s:%d' \
                        % (default_filetracker_host, DEFAULT_FILETRACKER_PORT)

        return internet.TCPClient(options['host'], int(options['port']),
                WorkerFactory())


class ServerOptions(usage.Options):
    optParameters = [
            ['worker-listen', 'w', '', "workers listen address"],
            ['worker-port', '', 7888, "workers port number"],
            ['rpc-listen', 'r', '', "RPC listen address"],
            ['rpc-port', '', 7889, "RPC listen port"],
            ['database', 'db', 'sioworkersd.sqlite', "database file path"],
            ]


class ServerServiceMaker(object):
    implements(service.IServiceMaker, IPlugin)
    tapname = 'sioworkersd'
    description = 'TODO'
    options = ServerOptions

    def makeService(self, options):

        db = DBWrapper(options['database'])

        workerm = WorkerManager(db)
        workerm.setServiceParent(db)

        taskm = TaskManager(db, workerm, FIFOScheduler(workerm))
        taskm.setServiceParent(db)

        rpc = siorpc.makeSite(workerm, taskm)
        internet.TCPServer(int(options['rpc-port']), rpc,
                interface=options['rpc-listen']).setServiceParent(db)

        internet.TCPServer(int(options['worker-port']), workerm.makeFactory(),
                interface=options['worker-listen']).setServiceParent(db)

        return db


workerMaker = WorkerServiceMaker()

serverMaker = ServerServiceMaker()
