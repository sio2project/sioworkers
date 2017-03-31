from sio.sioworkersd import server
from sio.protocol.rpc import TimeoutError
from twisted.application import service
from twisted.internet import reactor, defer
from twisted.logger import Logger

log = Logger()

TASK_TIMEOUT = 60 * 60


class WorkerGone(Exception):
    """Worker disconnected while executing task."""
    pass


class Worker(object):
    """Information about a worker.
    ``info``: clientInfo dictionary, passed from worker
        (see sio.protocol.worker.WorkerProtocol.getHelloData)
    ``tasks``: set() of currently executing ``task_id``s
    ``is_running_cpu_exec``: bool, True if the worker is executing cpu-exec
        job, and (because such jobs are exclusive) can't run any other job
    ``concurrency``: number of tasks that worker can handle at the same time
    """
    def __init__(self, info, tasks, is_running_cpu_exec):
        self.info = info
        self.tasks = tasks
        self.is_running_cpu_exec = is_running_cpu_exec
        self.concurrency = info['concurrency']
        self.can_run_cpu_exec = info['can_run_cpu_exec']
        # These arguemnts should have been already parsed with json.loads
        assert isinstance(self.concurrency, int)
        assert isinstance(self.can_run_cpu_exec, bool)


class WorkerManager(service.MultiService):
    def __init__(self):
        service.MultiService.__init__(self)
        self.workers = {}
        self.workerData = {}
        self.deferreds = {}
        self.serverFactory = None
        self.newWorkerCallback = None

    def makeFactory(self):
        f = server.WorkerServerFactory(self)
        self.serverFactory = f
        return f

    def notifyOnNewWorker(self, callback):
        if not callable(callback):
            raise ValueError()
        self.newWorkerCallback = callback

    @defer.inlineCallbacks
    def newWorker(self, uid, proto):
        log.info('New worker {w} uid={uid}', w=proto.name, uid=uid)
        name = proto.name
        if name in self.workers:
            proto.transport.loseConnection()
            log.warn('WARNING: Worker {w} connected twice and was dropped',
                    w=name)
            raise server.DuplicateWorker()
        running = yield proto.call('get_running', timeout=5)
        # if running is non-empty the worker is executing something
        if running:
            log.warn('Rejecting worker {w} because it is running tasks',
                    w=name)
            raise server.WorkerRejected()
        # if information received from worker doesn't meet expectations
        # reject it
        try:
            worker = Worker(proto.clientInfo, set(), False)
        except Exception, e:
            log.warn('Rejecting worker {w} because it sent invalid ({e})'
                    ' client info: {d}', w=name, e=e, d=proto.clientInfo)
            raise server.WorkerRejected()
        self.workers[name] = proto
        self.workerData[name] = worker
        if self.newWorkerCallback:
            self.newWorkerCallback(name)

    def workerLost(self, proto):
        wd = self.workerData[proto.name]
        # _free in runOnWorker will delete from wd.tasks, so copy here
        del self.workers[proto.name]
        del self.workerData[proto.name]
        # Those errbacks will try to reschedule, so they *must* be run *after*
        # this worker is removed from those dicts
        for i in wd.tasks.copy():
            self.deferreds[i].errback(WorkerGone())

    def getWorkers(self):
        return self.workerData

    def runOnWorker(self, worker, task):
        w = self.workers[worker]
        wd = self.workerData[worker]
        job_type = task['job_type']
        if wd.is_running_cpu_exec:
            raise RuntimeError(
                    'Tried to send task to worker running cpu-exec job')
        if len(wd.tasks) >= wd.concurrency:
            raise RuntimeError('Tried to send task to fully loaded worker')
        if job_type == 'cpu-exec':
            if wd.tasks:
                raise RuntimeError(
                        'Tried to send cpu-exec job to busy worker')
            if not wd.can_run_cpu_exec:
                raise RuntimeError(
                        "Tried to send cpu-exec job to worker which "
                        "isn't allowed to run them.")
            wd.is_running_cpu_exec = True
        tid = task['task_id']
        log.info('Running {job_type} {tid} on {w}',
                job_type=job_type, tid=tid, w=worker)
        wd.tasks.add(tid)
        d = w.call('run', task, timeout=TASK_TIMEOUT)
        self.deferreds[tid] = d

        def _free(x):
            wd.tasks.discard(tid)
            del self.deferreds[tid]
            if wd.is_running_cpu_exec and wd.tasks:
                log.critical('FATAL: impossible happened: worker was running '
                    'cpu-exec job, but still has tasks left. Aborting.')
                reactor.crash()
            wd.is_running_cpu_exec = False
            return x

        def _trap_timeout(failure):
            failure.trap(TimeoutError)
            # This is probably the ugliest, most blunt solution possible,
            # but it at least works. TODO kill the task on the worker.
            w.transport.loseConnection()
            log.warn('WARNING: Worker {w} timed out while executing {tid}',
                    w=worker, tid=tid)
            return failure

        d.addBoth(_free)
        d.addErrback(_trap_timeout)
        return d
