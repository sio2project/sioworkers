class Scheduler(object):
    """Abstract scheduler interface."""

    def __init__(self, manager):
        self.manager = manager

    def __unicode__(self):
        """Admin-friendly text representation of the queue.
        Used for debugging and displaying in admin panel."""
        raise NotImplementedError()

    def updateContest(self, contest_uid, priority, weight):
        """Update contest prioriy and weight in scheduler memory."""
        pass

    def addWorker(self, worker_id):
        """Will be called when a new worker appears."""
        pass

    def delWorker(self, worker_id):
        """Will be called when a worker disappears."""
        pass

    def addTask(self, env):
        """Add a new task to queue."""
        raise NotImplementedError()

    def delTask(self, task_id):
        """Will be called when a task is completed or cancelled."""
        raise NotImplementedError()

    def schedule(self):
        """Return a list of tasks to be executed now, as a list of pairs
        (task_id, worker_id)."""
        raise NotImplementedError()


def getDefaultSchedulerClassName():
    return 'sio.sioworkersd.scheduler.prioritizing.PrioritizingScheduler'
