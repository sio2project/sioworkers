# pylint: disable=no-name-in-module
from sio.sioworkersd.prioritizing_scheduler import PrioritizingScheduler
from sio.sioworkersd.fifo import FIFOScheduler
from nose.tools import assert_equals

# Worker class copied from manager.py to keep this test twisted-free :-)
class Worker(object):
    """Information about a worker.
    ``info``: clientInfo dictionary, passed from worker
        (see sio.protocol.worker.WorkerProtocol.getHelloData)
    ``tags``: set() of tags (strings)
    ``tasks``: set() of currently executing ``task_id``s
    ``exclusive``: bool, True if the worker is executing an exclusive task
    """
    def __init__(self, info, tags, tasks):
        self.info = info
        self.tags = tags
        self.tasks = tasks
        self.exclusive = False
        self.count_exclusive = 0
        self.concurrency = int(info.get('concurrency', 1))

    def printInfo(self):
        print '%s, %s, %s' % (str(self.info), str(self.tags), str(self.tasks))
# --------------------------------------------------------------------------#

def create_task(tid, ex, tags=None, prio=0):
    return {'task_id': tid,
            'exclusive': ex,
            'tags': tags or {'default'},
            'priority': prio}

class Manager(object):
    def __init__(self):
        self.workers = dict()
        self.tasks = dict()

    def assignTaskToWorker(self, wid, task):
        if task['exclusive']:
            self.workers[wid].count_exclusive += 1
            self.workers[wid].exclusive = True
        self.workers[wid].tasks.append(task['task_id'])

    def completeOneTask(self, wid):
        if self.workers[wid].tasks:
            tid = self.workers[wid].tasks[0]
            self.workers[wid].count_exclusive -= 1
            self.workers[wid].exclusive = self.workers[wid].count_exclusive > 0
            del self.tasks[tid]
            del self.workers[wid].tasks[0]

    def createWorker(self, wid, conc, tags=None):
        self.workers[wid] = Worker({'concurrency': conc},
            tags or {'default'}, [])

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
            if any([self.tasks[t]['exclusive'] for t in w.tasks]) \
                    and len(w.tasks) > 1:
                return 'Worker %s has non exclusive, exclusive task' % str(wid)
            if any([not (self.tasks[t]['tags'] & w.tags) for t in w.tasks]):
                return 'Worker %s checks job with non-matching tags' % str(wid)
        return 'OK'

    def showInnerState(self):
        for wid, w in self.workers.iteritems():
            print 'Worker (id: %d, concurr: %d, tags: %s) does %s' % \
                (wid, w.info['concurrency'], w.tags, w.tasks)

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
    assert_equals(sch.queue[-1][0], 200)
    man.completeOneTask(1)
    man.schedule(sch)
    assert_equals(sch.queue[-1][0], 300)
    man.completeOneTask(1)
    man.schedule(sch)
    man.completeOneTask(1)
    man.schedule(sch)
    assert_equals(len(sch.queue), 0)
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
    man.addTask(sch, create_task(100, True))
    man.schedule(sch)
    assert_equals(len(sch.queue), 0)
    man.addTask(sch, create_task(200, False))
    man.addTask(sch, create_task(300, False))
    man.addTask(sch, create_task(400, True))
    man.schedule(sch)
    man.schedule(sch)
    assert_equals(sch.queue[0], (400, True))
    assert_equals(len(sch.queue), 1)

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
    assert_equals(len(sch.queue), 0)
    man.completeOneTask(1)
    man.completeOneTask(2)
    man.completeOneTask(2)
    man.completeOneTask(3)
    assert not man.tasks

def test_exclusive():
    man = Manager()
    sch = PrioritizingScheduler(man)
    man.createWorker(1, 2, {'default'})
    man.addTask(sch, create_task(200, True, {'default'}, 100))
    man.addTask(sch, create_task(100, False, {'default'}, 100))
    man.schedule(sch)
    man.completeOneTask(1)
    man.schedule(sch)
    man.completeOneTask(1)
    assert not man.tasks

def test_exclusive_worker_gone():
    man = Manager()
    sch = PrioritizingScheduler(man)
    man.createWorker(1, 2, {'default'})
    man.addTask(sch, create_task(200, True, {'default'}, 100))
    man.addTask(sch, create_task(100, False, {'default'}, 100))
    man.schedule(sch)
    man.completeOneTask(1)
    man.deleteWorker(1)
    man.createWorker(2, 2, {'default'})
    man.schedule(sch)
    man.completeOneTask(2)
    assert not man.tasks

def test_exclusive_task_gone():
    man = Manager()
    sch = PrioritizingScheduler(man)
    man.createWorker(1, 2, {'default'})
    man.addTask(sch, create_task(200, True, {'default'}, 200))
    man.addTask(sch, create_task(100, False, {'default'}, 100))
    man.schedule(sch)
    man.completeOneTask(1)
    man.deleteTask(sch, 200)
    man.schedule(sch)
    man.completeOneTask(1)
    assert not man.tasks


def test_check_priorities():
    man = Manager()
    sch = PrioritizingScheduler(man)
    man.createWorker(1, 1, {'default'})
    man.addTask(sch, create_task(200, False, {'default'}, 200))
    man.addTask(sch, create_task(100, False, {'default'}, 100))
    man.schedule(sch)
    man.completeOneTask(1)
    assert 100 not in man.tasks
    assert 200 in man.tasks
    man.schedule(sch)
    man.completeOneTask(1)
    assert not man.tasks

def test_no_starvation():
    man = Manager()
    sch = PrioritizingScheduler(man)
    man.createWorker(1, 10, {'default'})
    man.addTask(sch, create_task(100, False, {'default'}, 100))
    man.addTask(sch, create_task(200, True, {'default'}, 200))
    man.addTask(sch, create_task(300, False, {'default'}, 300))
    man.schedule(sch)
    for _ in range(3):
        man.completeOneTask(1)
    assert 300 in man.tasks
    assert 200 in man.tasks
    man.schedule(sch)
    for _ in range(3):
        man.completeOneTask(1)
    assert 300 in man.tasks
    man.schedule(sch)
    man.completeOneTask(1)
    assert not man.tasks

def test_two_workers_enough():
    man = Manager()
    sch = PrioritizingScheduler(man)
    man.createWorker(1, 9, {'Alicja'})
    man.createWorker(2, 6, {'Bob'})
    for i in range(5):
        man.addTask(sch, create_task(i, False, {'Alicja'}, 100))
    for i in range(5):
        man.addTask(sch, create_task(i + 100, False, {'Alicja', 'Bob'}, 100))
    for i in range(5):
        man.addTask(sch, create_task(i + 200, False, {'Bob'}, 100))
    man.schedule(sch)
    for i in range(6):
        man.completeOneTask(2)
    for i in range(9):
        man.completeOneTask(1)
    assert not man.tasks

def test_two_workers_not_enough():
    man = Manager()
    sch = PrioritizingScheduler(man)
    man.createWorker(1, 9, {'Alicja'})
    man.createWorker(2, 6, {'Bob'})
    for i in range(3):
        man.addTask(sch, create_task(i, False, {'Alicja'}, 100))
    for i in range(5):
        man.addTask(sch, create_task(i + 100, False, {'Alicja', 'Bob'}, 100))
    for i in range(7):
        man.addTask(sch, create_task(i + 200, False, {'Bob'}, 100))
    man.schedule(sch)
    for i in range(10):
        man.completeOneTask(2)
    for i in range(10):
        man.completeOneTask(1)
    assert man.tasks

def test_locks():
    man = Manager()
    sch = PrioritizingScheduler(man)
    man.createWorker(1, 2, {'default'})
    man.createWorker(2, 2, {'default'})
    man.addTask(sch, create_task(11, False, {'default'}, 1))
    man.addTask(sch, create_task(12, False, {'default'}, 2))
    man.addTask(sch, create_task(13, True, {'default'}, 3))
    man.addTask(sch, create_task(14, True, {'default'}, 4))
    man.schedule(sch)
    for _ in range(4):
        man.completeOneTask(1)
        man.completeOneTask(2)
    assert man.tasks
    man.schedule(sch)
    for _ in range(4):
        man.completeOneTask(1)
        man.completeOneTask(2)
    assert not man.tasks

def test_big():
    man = Manager()
    sch = PrioritizingScheduler(man)
    man.createWorker(1, 9, {'A', 'B'})
    man.createWorker(2, 1, {'A', 'B', 'C'})
    man.createWorker(3, 4, {'B', 'C'})
    for i in range(5, 560):
        tags = set()
        if i % 17 == 0:
            tags.add('A')
        if i % 25 == 0:
            tags.add('B')
        if i % 2 == 0:
            tags.add('C')
        man.addTask(sch, create_task(i, i % 5 == 0, tags, 1000 - i))
    for _ in range(10):
        man.schedule(sch)
        for _ in range(9):
            man.completeOneTask(1)
            man.completeOneTask(2)
            man.completeOneTask(3)
    for i in range(10005, 10560):
        tags = set()
        if i % 17 == 0:
            tags.add('A')
        if i % 25 == 0:
            tags.add('B')
        if i % 2 == 0:
            tags.add('C')
        man.addTask(sch, create_task(i, i % 5 == 0, tags, 1000 - i))
    for i in range(500):
        man.schedule(sch)
        if i % 10 > 0:
            for _ in range(9):
                man.completeOneTask(1)
                man.completeOneTask(2)
                man.completeOneTask(3)
    for i in range(5, 560):
        if i % 17 > 0 and i % 25 > 0 and i % 2 > 0:
            assert i in man.tasks
    for i in range(10005, 10560):
        if i % 17 > 0 and i % 25 > 0 and i % 2 > 0:
            assert i in man.tasks
    for i in man.tasks:
        assert i % 17 > 0 and i % 25 > 0 and i % 2 > 0
