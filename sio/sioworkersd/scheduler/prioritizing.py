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
from sortedcontainers import SortedList, SortedSet

from sio.sioworkersd.scheduler import Scheduler
from sio.sioworkersd.utils import get_required_ram_for_job


class _WaitingTasksQueue(object):
    """A FIFO queue of tasks that keeps track of RAM limits.

    This class serves two purposes:
    1) It is a FIFO queue for tasks that also supports fast deletion.
    2) It keeps RAM requirements of all tasks in the queue in sorted order.

    This is necessary for the implementation of worker blocking,
    see ``PrioritingScheduler._getNumberOfBlockedAnyCpuWorkers()``
    for more details.
    """

    def __init__(self):
        self._dict = OrderedDict()
        self._tasks_required_ram = SortedList()

    def __contains__(self, task):
        return task in self._dict

    def __len__(self):
        return len(self._dict)

    def __nonzero__(self):
        return bool(self._dict)

    def add(self, task):
        self._dict[task] = True
        self._tasks_required_ram.add(task.required_ram_mb)

    def remove(self, task):
        del self._dict[task]
        self._tasks_required_ram.discard(task.required_ram_mb)

    def left(self):
        if self._dict:
            return self._dict.iteritems().next()[0]
        else:
            return None

    def popleft(self):
        task = self._dict.popitem(False)[0]
        self._tasks_required_ram.discard(task.required_ram_mb)
        return task

    def getTasksRequiredRam(self):
        return self._tasks_required_ram


class WorkerInfo(object):
    """A class responsible for tracking state of a single worker.

       There is exactly one instance of this class for each running worker.
    """

    def __init__(self, wid, wdata):
        assert wdata.concurrency > 0
        assert wdata.available_ram_mb > 0
        assert wdata.is_running_cpu_exec is False
        assert len(wdata.tasks) == 0
        # Immutable data
        self.id = wid
        self.concurrency = wdata.concurrency
        self.total_ram_mb = wdata.available_ram_mb
        self.cpu_enabled = wdata.can_run_cpu_exec

        # Mutable data
        # Whether this worker is currently running real-cpu task.
        self.is_running_real_cpu = False
        # Count of tasks that the worker currently has assigned.
        self.running_tasks = 0
        # Amount of RAM that can be potentially used by current tasks.
        self.used_ram_mb = 0

    def getQueueName(self):
        if (self.is_running_real_cpu
                or self.running_tasks == self.concurrency):
            return None
        elif self.cpu_enabled:
            return 'any-cpu'
        else:
            return 'vcpu-only'

    def getAvailableRam(self):
        """Returns the amount of RAM in MB this worker still has available.

        Note that this is only an estimation, since it's possible for tasks
        to exceed their declared RAM limit. Still, this is what the scheduler
        uses.
        """
        return self.total_ram_mb - self.used_ram_mb

    def getAvailableVcpuSlots(self):
        """Returns the number of vcpu tasks that can be assigned to worker.

        This value only depends on concurrency and the number of currently
        running tasks.
        """
        if self.is_running_real_cpu:
            return 0
        else:
            return self.concurrency - self.running_tasks

    def attachTask(self, task):
        assert self.running_tasks < self.concurrency
        assert self.used_ram_mb + task.required_ram_mb <= self.total_ram_mb
        assert self.is_running_real_cpu is False

        if task.real_cpu:
            assert self.cpu_enabled is True
            assert self.running_tasks == 0
            self.is_running_real_cpu = True

        self.used_ram_mb += task.required_ram_mb
        self.running_tasks += 1

    def detachTask(self, task):
        assert self.running_tasks >= 1
        assert (self.running_tasks == 1 or
            self.is_running_real_cpu is False)
        assert self.used_ram_mb >= task.required_ram_mb

        self.used_ram_mb -= task.required_ram_mb
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
                # lower available RAM (it should be just enough for the task).
                # such workers will be sorted first.
                lambda w: (w.running_tasks > 0,
                           w.getAvailableRam(),
                           w.id))
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
        self.waiting_real_cpu_tasks = _WaitingTasksQueue()

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

    def _getBestWorkerForVirtualCpuTask(
            self, queue, task_ram, prefer_busy=False):
        """Selects a worker from the queue best suited for a given task.

        The algorithm used picks a worker such that
        getAvailableRam() / getAvailableVcpuSlots() is the closest
        possible to task RAM limit between all viable workers.

        If prefer_busy flag is set to True, partially busy workers are given
        higher priority than completely empty ones.

        Returns None if there are no viable workers.
        """
        def suitability(worker):
            worker_optimal_ram = (
                    worker.getAvailableRam() / worker.getAvailableVcpuSlots())
            difference = abs(worker_optimal_ram - task_ram)

            if prefer_busy:
                return worker.running_tasks > 0, -difference
            else:
                return -difference

        assigned_worker = None
        for worker in queue:
            # getAvailableVcpuSlots() should never be 0 in normal conditions
            # because fully busy workers shouldn't be added to queues.
            if (worker.getAvailableRam() >= task_ram
                    and worker.getAvailableVcpuSlots() > 0):
                if (assigned_worker is None
                        or suitability(worker) > suitability(assigned_worker)):
                    assigned_worker = worker

        # Performance note: the execution time is linear in relation to
        # the worker queue size. This should not be a problem, but it's
        # possible in some cases to implement a logarithmic version
        # by using a suitable comparator as a key for worker queue SortedSet.

        return assigned_worker

    def _getBestVcpuOnlyWorkerForVirtualCpuTask(self, task_ram):
        """Returns a vcpu-only worker suitable for a task with given RAM limit.

        If there are no suitable workers (each worker is fully used, or
        doesn't have enough RAM available), returns None.
        """
        return self._getBestWorkerForVirtualCpuTask(
            self.workers_queues['vcpu-only'], task_ram)

    def _getBestAnyCpuWorkerForVirtualCpuTask(self, task_ram):
        """Returns any-cpu worker suitable for running given virtual-cpu task.

        If there are no suitable workers (each worker is fully used, or
        doesn't have enough RAM available), returns None.

        In this algorithm we prefer workers which are partially used, see
        _scheduleOnce for details.
        """
        return self._getBestWorkerForVirtualCpuTask(
            self.workers_queues['any-cpu'], task_ram, prefer_busy=True)

    def _getBestAnyCpuWorkerForRealCpuTask(self, task_ram):
        """Returns any-cpu worker suitable for running a given real-cpu task.

        The worker must be completely empty and have enough RAM (more than
        task RAM limit).

        If there are no such workers, returns None.
        """
        # This algorithm tries to pick with lowest available RAM that is
        # just enough for the task. To pick this worker, linear search is
        # performed on all free workers. Binary search could be used instead,
        # but it isn't necessary faster for small queue sizes.
        for worker in self.workers_queues['any-cpu']:
            if worker.running_tasks > 0:
                # All workers are partially busy.
                return None
            if worker.getAvailableRam() >= task_ram:
                return worker

        return None

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

        self._removeWorkerFromQueue(worker)
        worker.attachTask(task)
        self._insertWorkerToQueue(worker)

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
            self._removeWorkerFromQueue(task.assigned_worker)
            task.assigned_worker.detachTask(task)
            self._insertWorkerToQueue(task.assigned_worker)
        elif task in self.waiting_real_cpu_tasks:
            self.waiting_real_cpu_tasks.remove(task)
        else:
            self._removeTaskFromQueues(task)

    def _getNumberOfBlockedAnyCpuWorkers(self):
        """Returns the number of any cpu workers that are "blocked".

        "Blocked" workers should not be assigned new vcpu tasks, because
        there are waiting real-cpu tasks that must be scheduled ASAP.

        The number is calculated in a natural way: RAM requirements
        of waiting real-cpu tasks are compared with RAM amounts of
        real-cpu workers, and the returned value is the minimum number
        N such that _any_ N real-cpu workers can process all waiting
        tasks. Specifically, this means that the number of blocked
        workers may be higher than the number of waiting tasks, if
        there are workers that can not fit some tasks.

        If there is no such N (which may happen in a corner case
        when a huge task that is larger than any worker in the queue
        is added, and also when the queue is empty), the size of
        the any-cpu worker queue is returned (which means all of them
        should be considered blocked).
        """
        if (self.manager.minAnyCpuWorkerRam is None
                or not self.waiting_real_cpu_tasks):
            return 0

        waiting_real_cpu_tasks_ram = (
            self.waiting_real_cpu_tasks.getTasksRequiredRam())

        # This is the most common case, and we should handle this in O(1).
        if self.manager.minAnyCpuWorkerRam >= waiting_real_cpu_tasks_ram[-1]:
            return len(self.waiting_real_cpu_tasks)

        workers_ram = [
                w.available_ram_mb
                for _, w in self.manager.getWorkers().iteritems()
                if w.can_run_cpu_exec]

        workers_ram.sort()

        next_worker_index = 0
        # This list is sorted.
        for task_ram in waiting_real_cpu_tasks_ram:
            while (next_worker_index < len(workers_ram)
                    and workers_ram[next_worker_index] < task_ram):
                next_worker_index += 1

            if next_worker_index < len(workers_ram):
                next_worker_index += 1
            else:
                # All workers are blocked.
                return len(workers_ram)

        return next_worker_index

    def _scheduleOnce(self):
        """Selects one task to be executed.

           Returns a pair ``(task_id, worker_id)`` or ``None`` if it is not
           possible.
        """

        # If there is a virtual-cpu task, and a suitable vcpu-only worker,
        # associate them.
        if self.tasks_queues['virtual-cpu']:
            vcpu_task = self.tasks_queues['virtual-cpu'].chooseTask()
            if vcpu_task:
                vcpu_worker = self._getBestVcpuOnlyWorkerForVirtualCpuTask(
                    vcpu_task.required_ram_mb)
                if vcpu_worker:
                    self._removeTaskFromQueues(vcpu_task)
                    self._attachTaskToWorker(vcpu_task, vcpu_worker)
                    return vcpu_task.id, vcpu_worker.id

        # If there is an any-cpu worker suitable for the first queued real-cpu
        # task, associate them.
        # Usually any empty any-cpu worker will do, since worker RAM amount is
        # typically higher than all of the tasks RAM limits.
        waiting_rcpu_task = self.waiting_real_cpu_tasks.left()
        if waiting_rcpu_task:
            rcpu_worker = self._getBestAnyCpuWorkerForRealCpuTask(
                waiting_rcpu_task.required_ram_mb)
            if rcpu_worker:
                self.waiting_real_cpu_tasks.popleft()
                self._attachTaskToWorker(waiting_rcpu_task, rcpu_worker)
                return waiting_rcpu_task.id, rcpu_worker.id

        # The logic used below is that each queued real-cpu tasks "blocks"
        # one partially busy any-cpu worker from running virtual-cpu tasks.
        # If all partially busy workers are "blocked", we do not schedule
        # more tasks, instead we wait for them to become completely free to
        # process queued real-cpu tasks.
        #
        # The statement above is true if we make a natural assumption
        # that any-cpu workers' total RAM amount is greater than
        # all tasks' RAM limit, then we can "map" every blocked worker
        # to a queued task, because any worker will do.
        #
        # If this is not the case (which should be pretty rare), we need
        # to make sure that we block enough workers for them to handle all
        # tasks. Refer to _getNumberOfBlockedAnyCpuWorkers() for details on
        # how this is implemented.
        #
        # The logic above allows to assign any-cpu workers to both virtual-cpu
        # and real-cpu tasks without starving any of them.
        if (self._getAnyCpuQueueSize() > self._getNumberOfBlockedAnyCpuWorkers()
                and self.tasks_queues['both']):
            task = self.tasks_queues['both'].chooseTask()
            if not task.real_cpu:
                worker = self._getBestAnyCpuWorkerForVirtualCpuTask(
                    task.required_ram_mb)
                # It's possible that no worker has enough RAM for this task.
                # In this case, we do nothing and simply wait until some worker
                # (possibly vcpu-only) is now available.
                if worker:
                    self._removeTaskFromQueues(task)
                    self._attachTaskToWorker(task, worker)
                    return task.id, worker.id
            else:
                worker = self._getBestAnyCpuWorkerForRealCpuTask(
                    task.required_ram_mb)
                if worker:
                    self._removeTaskFromQueues(task)
                    self._attachTaskToWorker(task, worker)
                    return task.id, worker.id
                else:
                    # Reserve an any-cpu worker for this task.
                    self._removeTaskFromQueues(task)
                    self.waiting_real_cpu_tasks.add(task)

                    # There may be other tasks we can schedule right now.
                    return self._scheduleOnce()

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
