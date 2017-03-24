class Scheduler(object):
    """Abstract scheduler interface.
    """
    def __init__(self, manager):
        self.manager = manager

    def addTask(self, env):
        """Add a new task to queue."""
        raise NotImplementedError()

    def delTask(self, task_id):
        """Will be called when a task is completed or cancelled."""
        raise NotImplementedError()

    def __unicode__(self):
        """Admin-friendly text representation of the queue.
        Used for debugging and displaying in admin panel."""
        raise NotImplementedError()

    def schedule(self):
        """Return a list of tasks to be executed now, as a list of pairs
        (task_id, worker_id)."""
        raise NotImplementedError()


def get_default_scheduler_class_name():
    return 'sio.sioworkersd.scheduler.fifo.FIFOScheduler'
