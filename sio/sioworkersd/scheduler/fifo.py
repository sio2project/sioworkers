from sio.sioworkersd.scheduler import Scheduler
from collections import deque, namedtuple
from operator import attrgetter

QueuedTask = namedtuple('QueuedTask', ['id', 'job_type'])
WorkerInfo = namedtuple('WorkerInfo', ['id', 'task_cnt', 'concurrency'])

class FIFOScheduler(Scheduler):
    """ Scheduler that runs tasks in arrival order.
    """
    def __init__(self, manager):
        super(FIFOScheduler, self).__init__(manager)
        self.queue = deque()

    def addTask(self, env):
        self.queue.appendleft(QueuedTask(env['task_id'], env['job_type']))

    def delTask(self, tid):
        for i, task in enumerate(self.queue):
            if tid == task.id:
                del self.queue[i]
                break

    def __unicode__(self):
        return unicode(self.queue)

    def schedule(self):
        # Rather inefficient, but this scheduler is an example anyway
        free = []           # Workers without any task running on it.
        workers = deque()   # Workers with some space left.
        for wid, wdata in self.manager.getWorkers().iteritems():
            task_cnt = len(wdata.tasks)
            concurrency = int(wdata.concurrency)
            if wdata.is_running_cpu_exec or task_cnt >= concurrency:
                continue
            if task_cnt == 0:
                free.append(WorkerInfo(wid, 0, concurrency))
            else:
                workers.appendleft(WorkerInfo(wid, task_cnt, concurrency))
        free = deque(sorted(free, key=attrgetter('concurrency')))
        res = []
        while self.queue:
            if self.queue[-1].job_type == 'cpu-exec':
            # If this task is cpu-exec job, get free worker with smallest
            # concurrency.
                if not free:
                    break
                task = self.queue.pop()
                worker = free.popleft()
                res.append((task.id, worker.id))
            else:
            # If it's not, prefer busy workers. When there are only free ones,
            # choose worker with highest concurrency.
                worker = None
                if workers:
                    worker = workers.pop()
                elif free:
                    worker = free.pop()
                else:
                    break
                task = self.queue.pop()
                res.append((task.id, worker.id))
                if (worker.task_cnt + 1) < worker.concurrency:
                # If worker has some free space, use it again.
                    workers.append(
                            worker._replace(task_cnt=worker.task_cnt + 1))
        return res
