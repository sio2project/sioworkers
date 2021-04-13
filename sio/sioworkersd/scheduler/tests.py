# pylint: disable=no-name-in-module
from __future__ import absolute_import
from __future__ import print_function
from random import Random
import importlib

from sio.assertion_utils import eq_

from sio.sioworkersd.scheduler import getDefaultSchedulerClassName
from sio.sioworkersd.scheduler.prioritizing import PrioritizingScheduler
import six

# Constructors of all schedulers, used in generic tests.
schedulers = [PrioritizingScheduler]

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
        # These old tests don't account for RAM, so we just put a large value.
        self.available_ram_mb = 8192
        self.can_run_cpu_exec = can_run_cpu_exec

    def printInfo(self):
        print('%s, %s' % (str(self.info), str(self.tasks)))


# --------------------------------------------------------------------------#


class Manager(object):
    def __init__(self):
        self.contests = dict()
        self.workers = dict()
        self.tasks = dict()
        self.scheduler = None
        self.random = Random(0)

        # The tests here don't account for memory limits, so we just put
        # some bogus values.
        self.minAnyCpuWorkerRam = 4096
        self.maxAnyCpuWorkerRam = 4096
        self.minVcpuOnlyWorkerRam = 4096
        self.maxVcpuOnlyWorkerRam = 4096

    def _assignTaskToWorker(self, wid, task):
        assert task['assigned_worker_id'] is None
        task['assigned_worker_id'] = wid
        if task['job_type'] == 'cpu-exec':
            self.workers[wid].count_cpu_exec += 1
            self.workers[wid].is_running_cpu_exec = True
        self.workers[wid].tasks.append(task['task_id'])

    def _checkInnerState(self):
        for wid, w in six.iteritems(self.workers):
            if len(w.tasks) > w.info['concurrency']:
                return 'Worker %s has too many jobs - can have %s and has %d' % (
                    str(wid),
                    str(w.info['concurrency']),
                    len(w.tasks),
                )
            if (
                any([self.tasks[t]['job_type'] == 'cpu-exec' for t in w.tasks])
                and len(w.tasks) > 1
            ):
                return 'Worker %s is running cpu-exec task and other task' % str(wid)
        return 'OK'

    def _showInnerState(self):
        for wid, w in six.iteritems(self.workers):
            print(
                'Worker (id: %d, concurr: %d) does %s'
                % (wid, w.info['concurrency'], w.tasks)
            )

    def getWorkers(self):
        return self.workers

    def setScheduler(self, scheduler):
        self.scheduler = scheduler

    def updateContest(self, contest_uid, priority, weight):
        self.contests[contest_uid] = (priority, priority)
        self.scheduler.updateContest(contest_uid, priority, weight)

    def addWorker(self, wid, conc, can_run_cpu_exec=True):
        self.workers[wid] = Worker(
            {'concurrency': conc}, [], can_run_cpu_exec=can_run_cpu_exec
        )
        self.scheduler.addWorker(wid)

    def delWorker(self, wid):
        del self.workers[wid]
        self.scheduler.delWorker(wid)

    def addTask(self, tid, cpu_concerned, contest_uid=None, task_priority=0):
        task = {
            'task_id': tid,
            'job_type': 'cpu-exec' if cpu_concerned else 'vcpu-exec',
            'contest_uid': contest_uid,
            'task_priority': task_priority,
            'assigned_worker_id': None,
        }
        self.tasks[task['task_id']] = task
        self.scheduler.addTask(task)

    def completeOneTask(self, wid):
        if self.workers[wid].tasks:
            w_tasks = self.workers[wid].tasks
            tid_position = self.random.randint(0, len(w_tasks) - 1)
            # Swap with last element
            w_tasks[tid_position], w_tasks[len(w_tasks) - 1] = (
                w_tasks[len(w_tasks) - 1],
                w_tasks[tid_position],
            )
            tid = w_tasks.pop()
            self.workers[wid].count_cpu_exec -= 1
            self.workers[wid].is_running_cpu_exec = self.workers[wid].count_cpu_exec > 0
            del self.tasks[tid]
            self.scheduler.delTask(tid)

    def schedule(self):
        res = self.scheduler.schedule()
        for tid, wid in res:
            assert tid in self.tasks
            self._assignTaskToWorker(wid, self.tasks[tid])
        eq_(self._checkInnerState(), 'OK')


def testDefaultSchedulerExistence():
    module_name, class_name = getDefaultSchedulerClassName().rsplit('.', 1)
    # can throw ImportError and fail test
    module = importlib.import_module(module_name)
    assert hasattr(module, class_name)


def testCpuExec():
    for mk_sch in schedulers:
        man = Manager()
        sch = mk_sch(man)
        man.setScheduler(sch)
        man.addWorker(1, 2)
        man.updateContest(None, 0, 1)
        man.addTask(200, True)
        man.addTask(100, False)
        man.schedule()
        man.completeOneTask(1)
        assert man.tasks
        man.schedule()
        man.completeOneTask(1)
        assert not man.tasks


def testCpuExecWorkerGone():
    for mk_sch in schedulers:
        man = Manager()
        sch = mk_sch(man)
        man.setScheduler(sch)
        man.addWorker(1, 2)
        man.updateContest(1234, 4321, 4332)
        man.updateContest(1235, 5321, 1234)
        man.addTask(200, True, 1234, 11)
        man.addTask(100, False, 1235, 15)
        man.schedule()
        man.completeOneTask(1)
        man.delWorker(1)
        man.addWorker(2, 2)
        man.schedule()
        man.completeOneTask(2)
        assert not man.tasks


def testExclusiveTaskGone():
    man = Manager()
    sch = PrioritizingScheduler(man)
    man.setScheduler(sch)
    man.addWorker(1, 2, True)
    man.updateContest('Konkurs A', 1, 1)
    man.updateContest(('Konkurs', 'B'), 1, 10 ** 6)
    man.addTask(200, True, 'Konkurs A', 200)
    man.addTask(100, False, ('Konkurs', 'B'), 100)
    man.schedule()
    man.completeOneTask(1)
    man.schedule()
    man.completeOneTask(1)
    assert not man.tasks
    man.schedule()


def _randomTesting1(Scheduler, contests_count, workers_count, tasks_count):
    man = Manager()
    random = man.random
    sch = Scheduler(man)
    man.setScheduler(sch)

    created_tasks_count = 0
    created_workers_count = 0
    worker_ids = []

    while True:
        operations = []
        if created_tasks_count < tasks_count:
            operations.append(('addTask', 10))
        if created_workers_count < workers_count:
            operations.append(('addWorker', 10))
        if len(man.workers) >= 2:
            operations.append(('delWorker', 1))
        if len(man.tasks) >= 1:
            operations.append(('delTask', 5))
        if not operations:
            break
        operations.append(('schedule', 1))

        operation = None
        # Random weighted selection
        weight_sum = sum(op[1] for op in operations)
        r = random.randint(1, weight_sum)
        prefix_sum = 0
        for op in operations:
            prefix_sum += op[1]
            if prefix_sum >= r:
                operation = op[0]
                break

        if operation == 'addTask':
            created_tasks_count += 1
            tid = created_tasks_count
            cpu_concerned = bool(random.randint(0, 1))
            contest_uid = random.randint(1, contests_count)
            task_priority = random.randint(1, 10 ** 9)
            if not contest_uid in man.contests:
                man.updateContest(
                    contest_uid, random.randint(-3, 3), random.randint(1, 10 ** 6)
                )
            man.addTask(tid, cpu_concerned, contest_uid, task_priority)
        elif operation == 'addWorker':
            created_workers_count += 1
            wid = created_workers_count
            conc = random.randint(1, 50)
            if created_workers_count == 1:
                can_run_cpu_exec = True
            else:
                can_run_cpu_exec = random.randint(0, 10) >= 7
            worker_ids.append(wid)
            man.addWorker(wid, conc, can_run_cpu_exec)
        elif operation == 'delWorker':
            # First worker isn't removed, becouse we want to leave
            # at least one cpu-enabled worker.
            wid_position = random.randint(0 + 1, len(worker_ids) - 1)
            # Swap with last element
            worker_ids[wid_position], worker_ids[len(worker_ids) - 1] = (
                worker_ids[len(worker_ids) - 1],
                worker_ids[wid_position],
            )
            wid = worker_ids.pop()
            while man.workers[wid].tasks:
                man.completeOneTask(wid)
            man.delWorker(wid)
        elif operation == 'delTask':
            if worker_ids:
                wid = random.choice(worker_ids)
                if man.workers[wid].tasks:
                    man.completeOneTask(wid)
        elif operation == 'schedule':
            man.schedule()
        else:
            assert False
    man.schedule()
    while man.workers:
        wid = six.next(six.iterkeys(man.workers))
        while man.workers[wid].tasks:
            man.completeOneTask(wid)
        man.delWorker(wid)
    man.schedule()
    assert len(man.tasks) == 0
    assert len(man.workers) == 0
    # All tasks judged.


def testSmallRandom():
    for mk_sch in schedulers:
        _randomTesting1(mk_sch, 100, 100, 100)


def testBigRandom():
    _randomTesting1(PrioritizingScheduler, 10, 10 ** 3, 10 ** 3)
    _randomTesting1(PrioritizingScheduler, 10 ** 3, 10 ** 2, 10 ** 2)
