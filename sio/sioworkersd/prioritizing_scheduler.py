from sio.sioworkersd.scheduler import Scheduler
from random import shuffle
import heapq

class PrioritizingScheduler(Scheduler):
    """ I) This scheduler keeps a priority queue for each tag.
    When it has to schedule jobs:
    1) It iterates through all workers,
    2) It iterates through all tags of the worker in random order,
    3) For each tag in each worker:
        i) it checks how many new jobs can the worker carry out and
        ii) While this number is greater than zero:
            it removes the task from top of the priority queue connected
            with current tag.
        iii) If that job is not exclusive:
            a) the scheduler assigns it to the current worker
            b) and decrements the number of jobs which current worker can do.
        iii')Else if it is an exclusive job:
            a) the scheduler sets a lock on the current worker
            b) and decreases number of jobs the current worker can carry
            out to 0

    II) Those locks have a similar function as in readers-writers problem.
    When the locked worker completes each of its tasks (and thus
    is able to perform an exclusive job), the exclusive job that casused
    the lock is assigned to the worker, and the lock is released.

    III) The scheduler also takes caution that no job is done twice
    by keeping a dict of undone jobs. When it finds out that the job on
    the top of a priority queue has already been done
    (is not longer in the dict), it simply skips it.

    IV) Another moment when the scheduler has to take caution is when an
    exclusive job is waiting for a worker that no longer is available.
    In this case the scheduler re-adds this task to the priority queues.

    V)The meaning of the priorities:
    The lower the priority, the more important the task.
    """
    def __init__(self, manager):
        super(PrioritizingScheduler, self).__init__(manager)
        # set of all undone task as in paragraph III of docsting
        self.allTasks = dict()
        # locks as described in paragraph II of docsting
        self.locks = dict()
        self.reverse_locks = dict()
        # queues for tags as described in paragraph I of docsting
        self.queues = dict()

    def addTask(self, env):
        tid = env['task_id']
        ex = env['exclusive']
        tags = env['tags']
        prio = env.get('priority', 1000)
        self.allTasks[tid] = (prio, ex, set(tags))
        for tag in tags:
            if tag not in self.queues:
                self.queues[tag] = []
            # add task with task_id $tid to the priority queue of $tag
            heapq.heappush(self.queues[tag], (prio, tid))

    def delTask(self, tid):
        if tid in self.allTasks:
            del self.allTasks[tid]

    def __unicode__(self):
        return unicode(self.allTasks.keys())

    def schedule(self):
        ans = []
        workers = self.manager.getWorkers()
        local_lock = set()
        to_del = []
        for wid, tid in self.locks.iteritems():
        # in this loop we are checking if the locks (from paragraph II) are
        # still valid
            if not tid in self.allTasks:
            # the task has been deleted -- removing lock
                to_del.append(wid)
            elif not wid in workers:
            # the worker has been deleted -- re-adding task
            # as described in the paragraph IV of docstring
                to_del.append(wid)
                task = self.allTasks[tid]
                self.delTask(tid)
                self.addTask({'task_id': tid,
                                'exclusive': task[1],
                                'tags': task[2],
                                'priority': task[0]})
            elif len(workers[wid].tasks) == 0:
            # the worker has finished all of its non-exclusive jobs
            # and can perform an exlusive job that caused the lock
            # as described in paragraph II of docstring.
            # The local_lock variable makes sure that no other jobs will
            # be assigned to this worker in this turn
                ans.append((tid, wid))
                local_lock.add(wid)
                del self.allTasks[tid]
                to_del.append(wid)

        for wid in to_del:
            # one cannot delete from the structure one is iterating so
            # deletions had to be postponed to here
            tid = self.locks[wid]
            del self.locks[wid]
            del self.reverse_locks[tid]
        del to_del

        for wid, winfo in workers.iteritems():
            tags = list(winfo.tags)
            shuffle(tags)  # random order of tags
            limit = winfo.info['concurrency']
            ter = len(winfo.tasks)  # how many tasks this worker is doing now
            if wid in local_lock or wid in self.locks:
                # if there is lock on this worker it should not perform
                # any tasks
                continue
            if winfo.exclusive:
                # if this worker performs an exclusive task it should not
                # perform any additional tasks
                continue
            for tag in tags:
                queue = self.queues.get(tag, [])
                while queue and ter < limit:
                    # removing first element from the queue
                    # and saving its tag id in the tid variable
                    tid = heapq.heappop(queue)[1]
                    if not tid in self.allTasks or tid in self.reverse_locks:
                        # the task has been deleted, or it has set a lock
                        # on another worker
                        continue
                    exclusive = self.allTasks[tid][1]
                    if exclusive:
                        limit = 0
                        if ter == 0:
                            # the task is exclusive, but the worker is not
                            # doing any jobs.
                            # The task can be assigned right away.
                            ans.append((tid, wid))
                            self.delTask(tid)
                        else:
                            # the task is exclusive, but the worker is doing
                            # some jobs. The task has to set a lock and wait
                            self.locks[wid] = tid
                            self.reverse_locks[tid] = wid
                    else:
                        # the task is not exclusive. It can be assinged
                        # right away
                        ter = ter + 1
                        ans.append((tid, wid))
                        self.delTask(tid)
                if ter < limit:
                    # current worker is already full so no other jobs can
                    # be assigned to it
                    break
        return ans
