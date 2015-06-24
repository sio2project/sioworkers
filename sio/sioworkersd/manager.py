from twisted.application.service import Service
from sio.sioworkersd.server import WorkerServerFactory, DuplicateWorker
from twisted.internet import reactor, defer
from twisted.logger import Logger

log = Logger()

TASK_TIMEOUT = 60 * 15


class WorkerGone(Exception):
    """Worker disconnected while executing task."""
    pass


class Worker(object):
    """Information about a worker.
    ``info``: clientInfo dictionary, passed from worker
        (see sio.protocol.worker.WorkerProtocol.getHelloData)
    ``tags``: set() of tags (strings)
    ``tasks``: set() of currently executing ``task_id``s
    ``exclusive``: bool, True if the worker is executing an exclusive task
    """
    def __init__(self, info, tags, tasks, exclusive):
        self.info = info
        self.tags = tags
        self.tasks = tasks
        self.exclusive = exclusive


class WorkerManager(Service):
    def __init__(self, db):
        self.db = db
        self.workers = {}
        self.workerData = {}
        self.deferreds = {}
        self.serverFactory = None
        self.newWorkerCallback = None

    def makeFactory(self):
        f = WorkerServerFactory(self)
        self.serverFactory = f
        return f

    def notifyOnNewWorker(self, callback):
        if not callable(callback):
            raise ValueError()
        self.newWorkerCallback = callback

    @defer.inlineCallbacks
    def newWorker(self, uid, proto):
        name = proto.name
        if name in self.workers:
            proto.transport.loseConnection()
            log.warn('WARNING: Worker {w} connected twice and was dropped',
                    w=name)
            raise DuplicateWorker()
        present = yield self.db.runQuery(
                "select * from worker where name = ?;", (name,))
        tags = set()
        if present:
            tags = yield self.db.runQuery(
                    "select tag from worker_tag, worker where worker = ?;",
                    (name,))
            tags = {i[0] for i in tags}
        else:
            yield self.db.runOperation(
                    "insert into worker values (?)", (name,))
        self.workers[name] = proto
        self.workerData[name] = Worker(proto.clientInfo, tags, set(), False)
        if self.newWorkerCallback:
            self.newWorkerCallback(name)

    def workerLost(self, proto):
        wd = self.workerData[proto.name]
        # _free in runOnWorker will delete from wd.tasks, so copy here
        for i in wd.tasks.copy():
            self.deferreds[i].errback(WorkerGone())
        del self.workers[proto.name]
        del self.workerData[proto.name]

    def getWorkers(self):
        return self.workerData

    def addWorkerTag(self, wid, tag):
        assert isinstance(tag, str)
        if wid not in self.workerData:
            raise ValueError()
        # ignore if already present
        if tag not in self.workerData[wid].tags:
            self.workerData[wid].tags.add(tag)
            return self.db.runOperation(
                    "insert into worker_tag values (?, ?)", (tag, wid))

    def removeWorkerTag(self, wid, tag):
        assert isinstance(tag, str)
        if wid not in self.workerData or \
                tag not in self.workerData[wid].tags:
            raise ValueError()
        self.workerData[wid].tags.discard(tag)
        return self.db.runOperation(
                "delete from worker_tag where tag = ? and worker = ?",
                (tag, wid))

    def runOnWorker(self, worker, task):
        w = self.workers[worker]
        wd = self.workerData[worker]
        if wd.exclusive:
            raise RuntimeError('Tried to send task to exclusive worker')
        tid = task['task_id']
        log.info('Running {tid} on {w}', tid=tid, w=worker)
        if task.get('exclusive', True):
            if wd.tasks:
                raise RuntimeError(
                        'Tried to send exclusive task to busy worker')
            wd.exclusive = True
        wd.tasks.add(tid)
        d = w.call('run', task, timeout=TASK_TIMEOUT)
        self.deferreds[tid] = d

        def _free(x):
            wd.tasks.discard(tid)
            del self.deferreds[tid]
            if wd.exclusive and wd.tasks:
                log.critical('FATAL: impossible happened: worker was,'
                        'exclusive, but still has tasks left. Aborting.')
                reactor.crash()
            wd.exclusive = False
            return x
        d.addBoth(_free)
        return d
