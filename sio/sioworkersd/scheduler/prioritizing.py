"""Prioritizing Scheduler Algorithm

This is implementation of scheduler algorithm.

We define three measures of importance:
1. Contest priority
2. Contest weight
3. Task priority

Tasks are selected sequentially, independently from each other.

In the first phase of scheduling a contest is chosen. Contest priority
is the most important factor for selecting contests. Contests with
higher priority can cause starvation of other contests and this is the
desired behavior.

If there are multiple contests with same priority, they are judged in
an interleaved manner. The selection of contest is a probabilistic one,
with probability of being chosen proportional to the contest weight.

Task priorities are fully independent from what has been mentioned
so far.

In the second phase of scheduling a task is chosen from the contest
chosen in the first phase. The tasks within a contest are scheduled
for judging according to decreasing priorities. Tasks with the same
task priority within one contest are judged in arrival order.

We define two types of workers:
1. any-cpu worker (virtual cpu + real cpu)
2. vcpu-only worker (only virtual cpu)

If a worker has WORKER_ALLOW_RUN_CPU_EXEC setting set to true, the
worker is any-cpu worker. Otherwise it is vcpu-only worker.

We define two types of tasks:
1. real-cpu task
2. virtual-cpu task (virtual cpu)

Real-cpu task is cpu-exec job. It is judged on real cpu.
It can be judged only on any-cpu worker. Moreover it have to be
judged exclusively on a worker (at most one at a time).
Virtual-cpu task is non cpu-exec job. Most often it is judged on virtual
cpu. It can be judged on any worker (any-cpu or vcpu-only).
Virtual-cpu tasks can be judged simultaneously on one worker.
"""

from collections import OrderedDict
from random import Random
from sortedcontainers import SortedSet

from sio.sioworkersd.scheduler import Scheduler
from sio.sioworkersd.utils import get_required_ram_for_job


class _OrderedSet(object):
    """An ordered set implementation.

       We don't have any in the standard library, so we reuse OrderedDict,
       but do not use values for anything.

       collections.deque is not enough, because we need a fast remove().

       Only used methods are implemented.
    """

    def __init__(self):
        self.dict = OrderedDict()

    def __in__(self, value):
        return value in self.dict

    def __len__(self):
        return len(self.dict)

    def __nonzero__(self):
        return bool(self.dict)

    def add(self, value):
        self.dict[value] = True

    def remove(self, value):
        del self.dict[value]

    def popleft(self):
        return self.dict.popitem(False)[0]


class WorkerInfo(object):
    """A class responsible for tracking state of a single worker.

       There is exactly one instance of this class for each running worker.
    """

    def __init__(self, wid, wdata):
        assert wdata.concurrency >= 0
        assert wdata.is_running_cpu_exec is False
        assert len(wdata.tasks) == 0
        # Immutable data
        self.id = wid
        self.concurrency = wdata.concurrency
        self.cpu_enabled = wdata.can_run_cpu_exec
        # Mutable data
        # Whether this worker is currently running real-cpu task.
        self.is_running_real_cpu = False
        # Count of tasks that the worker currently has assigned.
        self.running_tasks = 0

    def getQueueName(self):
        if (self.is_running_real_cpu
                or self.running_tasks == self.concurrency):
            return None
        elif self.cpu_enabled:
            return 'any-cpu'
        else:
            return 'vcpu-only'

    def incTaskCounter(self, is_real_cpu):
        assert self.running_tasks < self.concurrency
        assert self.is_running_real_cpu is False
        if is_real_cpu:
            assert self.cpu_enabled is True
            assert self.running_tasks == 0
            self.is_running_real_cpu = True
        self.running_tasks += 1

    def decTaskCounter(self):
        assert self.running_tasks >= 1
        assert (self.running_tasks == 1 or
            self.is_running_real_cpu is False)
        self.running_tasks -= 1
        self.is_running_real_cpu = False


class TaskInfo(object):
    """Represent a single task.

       There is exactly one instance of this class for each task which have
       been added to scheduler and not deleted.
    """

    sequence_counter = 0

    def __init__(self, env, contest):
        assert ('task_priority' not in env or
            isinstance(env['task_priority'], (int, long)))
        # Immutable data
        self.id = env['task_id']
        self.real_cpu = (env['job_type'] == 'cpu-exec')
        self.required_ram_mb = get_required_ram_for_job(env)
        self.priority = env.get('task_priority', 0)
        self.contest = contest
        TaskInfo.sequence_counter += 1
        self.sequence_number = TaskInfo.sequence_counter
        # Mutable data
        self.assigned_worker = None


class ContestInfo(object):
    """Tracks priority and weight of a contest.

       There is exactly one instance of this class for each contest that have
       been ever added to scheduler.

       Instances of this class are never deleted.
    """

    def __init__(self, contest_uid, priority, weight):
        assert isinstance(priority, (int, long))
        assert isinstance(weight, (int, long))
        assert weight >= 1
        # Immutable data
        self.uid = contest_uid
        # Mutable data
        self.priority = priority
        self.weight = weight


class TasksQueues(object):
    """Per-contest priority queues of tasks.

       A single instance of this class stores one priority queue of
       tasks (:cls:`TaskInfo` instances) for each contest.
    """

    def __init__(self, random):
        self.random = random
        # Map from contest to SortedSet of queued tasks in that contest.
        self.queues = {}

    def __nonzero__(self):
        return bool(self.queues)

    def addTask(self, task):
        contest_queue = self.queues.setdefault(task.contest,
            SortedSet(key=
                # It's important that if we have many tasks with the same
                # priority, then we give priority to the oldest.
                # Otherwise, it would be unfair to the contestants if we
                # judged recently submitted solutions before the old ones.
                lambda t: (t.priority, -t.sequence_number)))
        assert task not in contest_queue
        contest_queue.add(task)

    def delTask(self, task):
        contest = task.contest
        contest_queue = self.queues[contest]
        contest_queue.remove(task)
        if not contest_queue:
            del self.queues[contest]

    def chooseTask(self):
        """Returns the highest-priority task from a contest chosen according
           to contest priorities and weights.

           It is not aware of tasks' types and workers' types.

           See the module docstring for a fuller description of the task choice
           strategy.
        """

        # Assumes that contests' weights are positive integers.
        # Contests' priorities may also be negative or zero.
        # It is possible to implement this function in logarithmic
        # complexity instead of linear. If you have many queued contests,
        # you should consider reimplementing it.

        assert self.queues

        max_contest_priority = None
        contests_weights_sum = None
        for contest in self.queues.iterkeys():
            current_contest_priority = contest.priority
            if (max_contest_priority is None
                    or current_contest_priority > max_contest_priority):
                max_contest_priority = current_contest_priority
                contests_weights_sum = 0
            if max_contest_priority == current_contest_priority:
                contests_weights_sum += contest.weight

        random_value = self.random.randint(1, contests_weights_sum)
        contests_weights_prefix_sum = 0
        best_contest = None
        for contest in self.queues.iterkeys():
            if contest.priority != max_contest_priority:
                continue
            contests_weights_prefix_sum += contest.weight
            if contests_weights_prefix_sum >= random_value:
                best_contest = contest
                break

        return self.queues[best_contest][-1]


class PrioritizingScheduler(Scheduler):
    """The prioritizing scheduler main class, implementing scheduler interface.

       It consist of two parts: Worker scheduler and Task scheduler.

       Worker scheduler is responsible for tracking state of all running
       workers. It is responsible for choosing the best worker for given task
       type, according to the priorities and weights.

       Task scheduler coordinates everything. It is responsible for tracking
       state of all tasks (it uses TasksQueues), scheduling and assigning
       tasks to workers. It is aware of tasks' types and workers' types and
       ensures that they match. It also protects real-cpu tasks against
       starvation.
    """

    def __init__(self, manager):
        super(PrioritizingScheduler, self).__init__(manager)
        self.random = Random(0)

        # Worker scheduling data
        self.workers = {}  # Map: worker_id -> worker
        # Queues of workers which are not full (free or partially free).
        self.workers_queues = {
            'vcpu-only': SortedSet(),
            'any-cpu': SortedSet(key=
                # For scheduling real-cpu tasks (which must run on
                # any-cpu workers) we need empty workers and we prefer
                # lower concurrency; such workers will be sorted first.
                lambda w: (w.running_tasks > 0, w.concurrency, w.id))
        }

        # Task scheduling data
        self.contests = {}  # Map: contest_uid -> contest
        self.tasks = {}  # Map: task_id -> task
        # Queues of tasks waiting for scheduling.
        # They do not contain tasks from self.waiting_real_cpu_tasks.
        self.tasks_queues = {
            'virtual-cpu': TasksQueues(self.random),
            'both': TasksQueues(self.random),
        }
        # Real-cpu tasks which have been scheduled,
        # but couldn't have been assigned to workers, because each
        # worker had already assigned at least one task.
        # See also: a huge comment in _scheduleOnce.
        self.waiting_real_cpu_tasks = _OrderedSet()

    def __unicode__(self):
        """Admin-friendly text representation of the queue.

           Used for debugging and displaying in the admin panel.
        """
        return unicode((self.tasks_queues, self.waiting_real_cpu_tasks))

    # Worker scheduling

    def _insertWorkerToQueue(self, worker):
        queue_name = worker.getQueueName()
        if queue_name is not None:
            self.workers_queues[queue_name].add(worker)

    def _removeWorkerFromQueue(self, worker):
        queue_name = worker.getQueueName()
        if queue_name is not None:
            self.workers_queues[queue_name].remove(worker)

    def _incWorkerTaskCounter(self, worker, is_real_cpu):
        self._removeWorkerFromQueue(worker)
        worker.incTaskCounter(is_real_cpu)
        self._insertWorkerToQueue(worker)

    def _decWorkerTaskCounter(self, worker):
        self._removeWorkerFromQueue(worker)
        worker.decTaskCounter()
        self._insertWorkerToQueue(worker)

    def addWorker(self, worker_id):
        """Will be called when a new worker appears."""
        worker = WorkerInfo(worker_id,
            self.manager.getWorkers()[worker_id])
        self.workers[worker_id] = worker
        self._insertWorkerToQueue(worker)

    def delWorker(self, worker_id):
        """Will be called when a worker disappears."""
        worker = self.workers[worker_id]
        assert worker.running_tasks == 0
        del self.workers[worker_id]
        self._removeWorkerFromQueue(worker)

    def _getAnyCpuQueueSize(self):
        return len(self.workers_queues['any-cpu'])

    def _getBestVcpuOnlyWorkerForVirtualCpuTask(self):
        """Returns the best available vcpu-only worker
        for running next virtual-cpu task.

        If there is no such workers (each worker is fully used),
        returns None.
        In this algorithm we don't differentiate vcpu-only workers,
        so we can return whichever vcpu-only worker. We return last
        from queue.
        """
        return self.workers_queues['vcpu-only'][-1] \
            if self.workers_queues['vcpu-only'] else None

    def _getBestAnyCpuWorkerForVirtualCpuTask(self):
        """Returns the best available any-cpu worker
        for running next virtual-cpu task.

        If there is no such workers (each worker is fully used),
        returns None.
        In this algorithm we prefer workers which are partially used
        and with higher concurrency. We return last worker form any-cpu
        workers queue which is sorted by (w.running_tasks > 0,
        w.concurrency, w.id).
        """
        # If there is available vcpu-only worker, we shouldn't be
        # choosing any-cpu worker for virtual-cpu task, because it
        # is unreasonable.
        assert self._getBestVcpuOnlyWorkerForVirtualCpuTask() is None
        return self.workers_queues['any-cpu'][-1] \
            if self.workers_queues['any-cpu'] else None

    def _getBestAnyCpuWorkerForRealCpuTask(self):
        """Return the best available (completely empty) any-cpu worker
        for running next real-cpu task.

        If there is no such workers (each worker is used),
        returns None.
        Real-cpu task can only be run on any-cpu worker so this
        function returns the best worker for real-cpu task.
        In this algorithm we prefer workers with lower concurrency. We
        return first worker from any-cpu workers queue which is sorted
        by (w.running_tasks > 0, w.concurrency, w.id).
        """
        if not self.workers_queues['any-cpu']:
            return None
        worker = self.workers_queues['any-cpu'][0]
        return worker if worker.running_tasks == 0 else None

    # Task scheduling

    def updateContest(self, contest_uid, priority, weight):
        """Update contest priority and weight in scheduler memory."""
        assert isinstance(priority, (int, long))
        assert isinstance(weight, (int, long))
        assert weight >= 1
        contest = self.contests.get(contest_uid)
        if contest is None:
            contest = ContestInfo(contest_uid, priority, weight)
            self.contests[contest_uid] = contest
        else:
            contest.priority = priority
            contest.weight = weight

    def _addTaskToQueues(self, task):
        if not task.real_cpu:
            self.tasks_queues['virtual-cpu'].addTask(task)
        self.tasks_queues['both'].addTask(task)

    def _removeTaskFromQueues(self, task):
        if not task.real_cpu:
            self.tasks_queues['virtual-cpu'].delTask(task)
        self.tasks_queues['both'].delTask(task)

    def _attachTaskToWorker(self, task, worker):
        assert task.assigned_worker is None
        task.assigned_worker = worker
        self._incWorkerTaskCounter(worker, task.real_cpu)

    def addTask(self, env):
        """Add a new task to queue."""
        assert env['contest_uid'] in self.contests
        task = TaskInfo(env, self.contests[env['contest_uid']])
        assert task.id not in self.tasks
        self.tasks[task.id] = task
        self._addTaskToQueues(task)

    def delTask(self, task_id):
        """Will be called when a task is completed or cancelled."""
        assert task_id in self.tasks
        task = self.tasks.pop(task_id)
        if task.assigned_worker:
            self._decWorkerTaskCounter(task.assigned_worker)
        elif task in self.waiting_real_cpu_tasks:
            self.waiting_real_cpu_tasks.remove(task)
        else:
            self._removeTaskFromQueues(task)

    def _scheduleOnce(self):
        """Selects one task to be executed.

           Returns a pair ``(task_id, worker_id)`` or ``None`` if it is not
           possible.
        """

        # If there is vcpu-only worker and virtual-cpu task,
        # associate them.
        worker = self._getBestVcpuOnlyWorkerForVirtualCpuTask()
        if worker is not None and self.tasks_queues['virtual-cpu']:
            task = self.tasks_queues['virtual-cpu'].chooseTask()
            self._removeTaskFromQueues(task)
            self._attachTaskToWorker(task, worker)
            return (task.id, worker.id)

        # If there is an empty any-cpu worker and we have
        # a blocked real cpu task, associate them.
        # We want to run blocked (waiting) real-cpu task immediately
        # when this becomes possible.
        worker = self._getBestAnyCpuWorkerForRealCpuTask()
        if worker is not None and self.waiting_real_cpu_tasks:
            task = self.waiting_real_cpu_tasks.popleft()
            self._attachTaskToWorker(task, worker)
            return (task.id, worker.id)

        # Each waiting real-cpu task blocks one any-cpu worker
        # (but not fixed one) against running virtual-cpu tasks.
        # After previous if statement, we know that if there is
        # waiting real-cpu task, there is no completely empty
        # real-cpu worker.
        # If we have more waiting real-cpu tasks then available
        # (partially free) any-cpu workers we give up and don't choose
        # new task.
        # This causes that count of waiting real-cpu tasks is limited
        # by number of any-cpu workers in queue.
        # This also causes that we don't starve real-cpu tasks, because
        # for real-cpu task we always choose first worker from any-cpu
        # queue and for virtual-cpu task from that queue we always
        # choose last worker. Partially used any-cpu workers are always
        # sorted in the same order in that queue.
        # If there are more partially free any-cpu workers
        # than waiting real-cpu task, we can use remaining workers for
        # virtual-cpu tasks.
        # We choose real-cpu and virtual-cpu tasks from the same
        # task queue ('both') so we don't discriminate real-cpu or
        # virtual-cpu tasks. But real-cpu tasks could wait longer
        # for empty worker (blocking virtual-cpu tasks).
        if (self._getAnyCpuQueueSize() > len(self.waiting_real_cpu_tasks)
                and self.tasks_queues['both']):
            task = self.tasks_queues['both'].chooseTask()
            self._removeTaskFromQueues(task)
            if not task.real_cpu:
                worker = self._getBestAnyCpuWorkerForVirtualCpuTask()
                self._attachTaskToWorker(task, worker)
                return (task.id, worker.id)
            else:
                worker = self._getBestAnyCpuWorkerForRealCpuTask()
                if worker is not None:
                    self._attachTaskToWorker(task, worker)
                    return (task.id, worker.id)
                else:
                    # Reserve one more any-cpu worker for this task.
                    self.waiting_real_cpu_tasks.add(task)
                    return None

        # Sorry, no match...
        return None

    def schedule(self):
        """Return a list of tasks to be executed now, as a list of pairs
           (task_id, worker_id).
        """
        result = []
        while True:
            association = self._scheduleOnce()
            if association is None:
                break
            result.append(association)
        return result
