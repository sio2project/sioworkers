# pylint: disable=no-name-in-module
from sio.sioworkersd.scheduler.fifo import FIFOScheduler
from nose.tools import assert_equals

# Constructors of all schedulers, used in generic tests.
schedulers = [FIFOScheduler]

# Worker class copied from manager.py to keep this test twisted-free :-)
class Worker(object):
    """Information about a worker.
    ``info``: clientInfo dictionary, passed from worker
        (see sio.protocol.worker.WorkerProtocol.getHelloData)
    ``tasks``: set() of currently executing ``task_id``s
    ``is_running_cpu_exec``: bool, True if the worker is running cpu-exec job
    """
    def __init__(self, info, tasks, can_run_cpu_exec=True):
        self.info = info
        self.tasks = tasks
        self.is_running_cpu_exec = False
        self.count_cpu_exec = 0
        self.concurrency = int(info.get('concurrency', 1))
        self.can_run_cpu_exec = can_run_cpu_exec

    def printInfo(self):
        print '%s, %s' % (str(self.info), str(self.tasks))
# --------------------------------------------------------------------------#

def create_task(tid, ex, prio=0):
    return {'task_id': tid,
            'job_type': 'cpu-exec' if ex else 'vcpu-exec',
            'priority': prio}

class Manager(object):
    def __init__(self):
        self.workers = dict()
        self.tasks = dict()

    def assignTaskToWorker(self, wid, task):
        if task['job_type'] == 'cpu-exec':
            self.workers[wid].count_cpu_exec += 1
            self.workers[wid].is_running_cpu_exec = True
        self.workers[wid].tasks.append(task['task_id'])

    def completeOneTask(self, wid):
        if self.workers[wid].tasks:
            tid = self.workers[wid].tasks[0]
            self.workers[wid].count_cpu_exec -= 1
            self.workers[wid].is_running_cpu_exec = \
                    self.workers[wid].count_cpu_exec > 0
            del self.tasks[tid]
            del self.workers[wid].tasks[0]

    def createWorker(self, wid, conc, can_run_cpu_exec=True):
        self.workers[wid] = Worker({'concurrency': conc}, [],
                can_run_cpu_exec=can_run_cpu_exec)

    def deleteWorker(self, wid):
        del self.workers[wid]

    def getWorkers(self):
        return self.workers

    def addTask(self, sch, task):
        self.tasks[task['task_id']] = task
        sch.addTask(task)

    def deleteTask(self, sch, tid):
        del self.tasks[tid]
        sch.delTask(tid)

    def schedule(self, sch):
        res = sch.schedule()
        for tid, wid in res:
            assert tid in self.tasks
            self.assignTaskToWorker(wid, self.tasks[tid])
        assert_equals(self.checkInnerState(), 'OK')

    def checkInnerState(self):
        for wid, w in self.workers.iteritems():
            if len(w.tasks) > w.info['concurrency']:
                return 'Worker %s has too many jobs - can have %s and has %d' \
                    % (str(wid), str(w.info['concurrency']), len(w.tasks))
            if any([self.tasks[t]['job_type'] == 'cpu-exec'
                        for t in w.tasks]) and len(w.tasks) > 1:
                return 'Worker %s is running cpu-exec task and other task' \
                        % str(wid)
        return 'OK'

    def showInnerState(self):
        for wid, w in self.workers.iteritems():
            print 'Worker (id: %d, concurr: %d) does %s' % \
                (wid, w.info['concurrency'], w.tasks)

def test_fifo():
    man = Manager()
    sch = FIFOScheduler(man)
    man.createWorker(1, 2)
    man.addTask(sch, create_task(100, True))
    man.addTask(sch, create_task(200, False))
    man.addTask(sch, create_task(300, True))
    man.addTask(sch, create_task(400, False))
    man.addTask(sch, create_task(500, False))
    man.schedule(sch)
    assert_equals(sch.queues['cpu+vcpu'][-1][0], 200)
    man.completeOneTask(1)
    man.schedule(sch)
    assert_equals(sch.queues['cpu+vcpu'][-1][0], 300)
    man.completeOneTask(1)
    man.schedule(sch)
    man.completeOneTask(1)
    man.schedule(sch)
    assert_equals(len(sch.queues['cpu+vcpu']), 0)
    man.completeOneTask(1)
    man.completeOneTask(1)
    assert not man.tasks

def test_fifo_many():
    man = Manager()
    sch = FIFOScheduler(man)
    man.createWorker(1, 2)
    man.createWorker(2, 2)
    man.createWorker(3, 2)
    man.addTask(sch, create_task(100, True))
    man.addTask(sch, create_task(200, True))
    man.schedule(sch)
    assert_equals(len(sch.queues['cpu+vcpu']), 0)
    man.addTask(sch, create_task(300, False))
    man.addTask(sch, create_task(400, False))
    man.addTask(sch, create_task(500, True))
    man.schedule(sch)
    man.schedule(sch)
    assert_equals(sch.queues['cpu+vcpu'][-1][0], 500)
    assert_equals(len(sch.queues['cpu+vcpu']), 1)

def test_fifo_greed():
    man = Manager()
    sch = FIFOScheduler(man)
    man.createWorker(1, 1)
    man.createWorker(2, 2)
    man.createWorker(3, 1)
    man.addTask(sch, create_task(100, True))
    man.addTask(sch, create_task(200, False))
    man.schedule(sch)
    man.addTask(sch, create_task(300, True))
    man.addTask(sch, create_task(400, False))
    man.schedule(sch)
    assert_equals(len(sch.queues['cpu+vcpu']), 0)
    man.completeOneTask(1)
    man.completeOneTask(2)
    man.completeOneTask(2)
    man.completeOneTask(3)
    assert not man.tasks

def test_cpu_exec():
    for mk_sch in schedulers:
        man = Manager()
        sch = mk_sch(man)
        man.createWorker(1, 2)
        man.addTask(sch, create_task(200, True, 100))
        man.addTask(sch, create_task(100, False, 100))
        man.schedule(sch)
        man.completeOneTask(1)
        assert man.tasks
        man.schedule(sch)
        man.completeOneTask(1)
        assert not man.tasks

def test_cpu_exec_worker_gone():
    for mk_sch in schedulers:
        man = Manager()
        sch = mk_sch(man)
        man.createWorker(1, 2)
        man.addTask(sch, create_task(200, True, 100))
        man.addTask(sch, create_task(100, False, 100))
        man.schedule(sch)
        man.completeOneTask(1)
        man.deleteWorker(1)
        man.createWorker(2, 2)
        man.schedule(sch)
        man.completeOneTask(2)
        assert not man.tasks
