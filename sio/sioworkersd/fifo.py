from sio.sioworkersd.scheduler import Scheduler
from collections import deque

class FIFOScheduler(Scheduler):
    def __init__(self, manager):
        super(FIFOScheduler, self).__init__(manager)
        self.queue = deque()

    def addTask(self, env):
        tid = env['task_id']
        self.queue.appendleft(tid)

    def delTask(self, tid):
        if tid in self.queue:
            self.queue.remove(tid)

    def __unicode__(self):
        return unicode(self.queue)

    def schedule(self):
        workers = self.manager.getWorkers()
        # Horribly inefficient, but this scheduler is an example anyway
        ret = []
        used = set()
        while self.queue:
            chosen = None
            for wid, data in workers.iteritems():
                if not data.tasks and wid not in used:
                    chosen = wid
                    break
            if chosen:
                t = self.queue.pop()
                ret.append((t, chosen))
                used.add(chosen)
            else:
                break
        return ret
