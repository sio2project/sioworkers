import urlparse
import importlib
import platform
from zope.interface import implements

from twisted.python import usage
from twisted.plugin import IPlugin
from twisted.application import service
from twisted.application import internet

from sio.protocol.worker import WorkerFactory
from filetracker.servers.run import DEFAULT_PORT as DEFAULT_FILETRACKER_PORT
import os
from sio.sioworkersd.workermanager import WorkerManager
from sio.sioworkersd.scheduler import get_default_scheduler_class_name
from sio.sioworkersd.taskmanager import TaskManager
from sio.sioworkersd.db import DBWrapper
from sio.sioworkersd import siorpc


def _host_from_url(url):
    return urlparse.urlparse(url).hostname


class WorkerOptions(usage.Options):
    # TODO: default concurrency to number of detected cpus
    optParameters = [['port', 'p', 7888, "sioworkersd port number", int],
                     ['concurrency', 'c', 1, "maximum concurrent jobs", int],
                     ['name', 'n', platform.node(), "worker name"]]
    optFlags = [['can-run-cpu-exec', None,
                    "Mark this worker as suitable for running tasks, which "
                    "are judged in safe mode on cpu (without oitimetool). "
                    "Has effect only for tasks received from oioioi instances "
                    "with USE_UNSAFE_EXEC disabled. All workers with this "
                    "option enabled should have same cpu. "]]

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
        return internet.TCPClient(options['host'], options['port'],
                WorkerFactory(
                    concurrency=options['concurrency'],
                    # Twisted argument parser set this to 0 or 1.
                    can_run_cpu_exec=bool(options['can-run-cpu-exec']),
                    name=options['name']))


class ServerOptions(usage.Options):
    optParameters = [
            ['worker-listen', 'w', '', "workers listen address"],
            ['worker-port', '', 7888, "workers port number"],
            ['rpc-listen', 'r', '', "RPC listen address"],
            ['rpc-port', '', 7889, "RPC listen port"],
            ['database', 'db', 'sioworkersd.sqlite', "database file path"],
            ['scheduler', 's', get_default_scheduler_class_name(),
                 "scheduler class"],
            ]


class ServerServiceMaker(object):
    implements(service.IServiceMaker, IPlugin)
    tapname = 'sioworkersd'
    description = 'TODO'
    options = ServerOptions

    def makeService(self, options):

        db = DBWrapper(options['database'])

        workerm = WorkerManager()

        sched_module, sched_class = options['scheduler'].rsplit('.', 1)
        try:
            SchedulerClass = \
                getattr(importlib.import_module(sched_module), sched_class)
        except ImportError:
            print "[ERROR] Invalid scheduler module: " + sched_module + "\n"
            raise
        except AttributeError:
            print "[ERROR] Invalid scheduler class: " + sched_class + "\n"
            raise

        taskm = TaskManager(db, workerm, SchedulerClass(workerm))
        taskm.setServiceParent(db)

        rpc = siorpc.makeSite(workerm, taskm)
        internet.TCPServer(int(options['rpc-port']), rpc,
                interface=options['rpc-listen']).setServiceParent(db)

        internet.TCPServer(int(options['worker-port']), workerm.makeFactory(),
                interface=options['worker-listen']).setServiceParent(db)

        return db


workerMaker = WorkerServiceMaker()

serverMaker = ServerServiceMaker()
