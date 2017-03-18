from sio.sioworkersd.scheduler import Scheduler
from collections import deque, namedtuple


# Type can be either cpu (for cpu-exec tasks) or vcpu (for others).
QueuedTask = namedtuple('QueuedTask', ['id', 'type'])


class WorkerInfo(object):
    """Wrapper around worker data, simulates changing worker state during
       scheduling process without actually sending anything to it. It is
       recreated for each scheduling process.
    """
    def __init__(self, wid, wdata):
        self.id = wid
        self.concurrency = wdata.concurrency
        self.tasks_count = len(wdata.tasks)
        self.can_run_cpu_exec = wdata.can_run_cpu_exec
        self.is_running_cpu_exec = wdata.is_running_cpu_exec

    def can_run(self, task):
        if self.is_running_cpu_exec or (self.tasks_count >= self.concurrency):
            return False
        else:
            if task.type == 'cpu':
                return self.can_run_cpu_exec and self.tasks_count == 0
            else:
                return True

    def assign(self, task):
        assert self.can_run(task)
        if task.type == 'cpu':
            self.is_running_cpu_exec = True
        self.tasks_count += 1


class FIFOScheduler(Scheduler):
    """Scheduler that runs tasks in arrival order.

       First try scheduling as many tasks as possible only using workers
       that can't run cpu-exec jobs. Then add remaining workers and schedule
       all tasks together.
    """
    def __init__(self, manager):
        super(FIFOScheduler, self).__init__(manager)
        # Set of tasks that currently are in queue.
        self.tasks = set()
        # Two queues, on for all tasks ('cpu+vcpu') and other for non
        # cpu-exec tasks ('vcpu').
        self.queues = {'cpu+vcpu': deque(), 'vcpu': deque()}

    def addTask(self, env):
        tid = env['task_id']
        task = QueuedTask(tid,
                'cpu' if env['job_type'] == 'cpu-exec' else 'vcpu')
        if task.type == 'vcpu':
            self.queues['vcpu'].appendleft(task)
        self.queues['cpu+vcpu'].appendleft(task)
        self.tasks.add(tid)

    def delTask(self, tid):
        if tid not in self.tasks:
            return
        self.tasks.remove(tid)
        for queue in self.queues.itervalues():
            for i, task in enumerate(queue):
                if tid == task.id:
                    del queue[i]
                    break

    def __unicode__(self):
        return unicode(self.queue)

    def _schedule_queue_with(self, queue, workers):
        """Schedule tasks from a queue using given workers.
        """
        result = []
        while queue:
            # Some tasks may have been already executed, skip them.
            if queue[-1].id not in self.tasks:
                queue.pop()
                continue
            if queue[-1].type == 'cpu':
                workers_queue = workers['cpu+vcpu']
            else:
                workers_queue = workers['vcpu']
            # Some workers may have changed, skip as many as needed.
            while workers_queue and not workers_queue[-1].can_run(queue[-1]):
                workers_queue.pop()
            if not workers_queue:
                break
            task = queue.pop()
            worker = workers_queue[-1]
            worker.assign(task)
            result.append((task.id, worker.id))
            self.tasks.remove(task.id)
        return result

    def schedule(self):
        # Map from types of tasks worker can run ('cpu+vcpu' for workers that
        # can run every type of job and 'vcpu' for workers that can't run
        # cpu-exec jobs) to deques of workers. A worker may belong to any
        # number of deques.
        workers = {'cpu+vcpu': [], 'vcpu': []}
        for wid, wdata in self.manager.getWorkers().iteritems():
            worker = WorkerInfo(wid, wdata)
            if worker.tasks_count >= worker.concurrency \
                    or worker.is_running_cpu_exec:
                continue
            workers['vcpu'].append(worker)
            if worker.can_run_cpu_exec and worker.tasks_count == 0:
                workers['cpu+vcpu'].append(worker)

        # Make it actually a map of sorted deques. Be greedy. For vcpu
        # jobs prefer workers that can't run cpu-exec jobs, then prefer
        # workers with huge concurrency. For cpu jobs prefer workers
        # with small concurrency.
        workers['vcpu'] = deque(sorted(workers['vcpu'],
            key=lambda w: (not w.can_run_cpu_exec, w.concurrency)))
        workers['cpu+vcpu'] = deque(sorted(workers['cpu+vcpu'],
            key=lambda w: w.concurrency, reverse=True))

        result = self._schedule_queue_with(self.queues['cpu+vcpu'], workers)
        while workers['vcpu'] and workers['vcpu'][0].can_run_cpu_exec:
            workers['vcpu'].popleft()
        result += self._schedule_queue_with(self.queues['vcpu'], workers)
        return result
