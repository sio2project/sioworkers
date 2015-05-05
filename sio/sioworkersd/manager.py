from twisted.application.service import Service
from sio.sioworkersd.server import WorkerServerFactory, DuplicateWorker
from twisted.internet import reactor, defer

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
        n = proto.name
        if n in self.workers:
            proto.transport.loseConnection()
            print 'WARNING: Worker %s connected twice and was dropped' % n
            raise DuplicateWorker()
        present = yield self.db.runQuery(
                "select * from worker where name = ?;", (n,))
        tags = set()
        if present:
            tags = yield self.db.runQuery(
                    "select tag from worker_tag, worker where worker = ?;",
                    (n,))
            tags = {i[0] for i in tags}
        else:
            yield self.db.runOperation(
                    "insert into worker values (?)", (n,))
        self.workers[n] = proto
        self.workerData[n] = Worker(proto.clientInfo, tags, set(), False)
        if self.newWorkerCallback:
            self.newWorkerCallback(n)

    def workerLost(self, proto):
        wd = self.workerData[proto.name]
        for i in wd.tasks:
            i.errback(WorkerGone())
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
                "delete from worker_tag where tag = ? and id = ?",
                (tag, wid))

    def runOnWorker(self, worker, task):
        w = self.workers[worker]
        wd = self.workerData[worker]
        if wd.exclusive:
            raise RuntimeError('Tried to send task to exclusive worker')
        tid = task['task_id']
        print 'Running %s on %s' % (tid, worker)
        if task.get('exclusive', True):
            if wd.tasks:
                raise RuntimeError(
                        'Tried to send exclusive task to busy worker')
            wd.exclusive = True
        wd.tasks.add(tid)
        d = w.call('run', task)

        def _free(x):
            wd.tasks.discard(tid)
            if wd.exclusive and wd.tasks:
                print 'FATAL: impossible happened: worker was exclusive,'\
                        'but still has tasks left. Aborting.'
                reactor.crash()
            wd.exclusive = False
            return x
        d.addBoth(_free)
        return d
