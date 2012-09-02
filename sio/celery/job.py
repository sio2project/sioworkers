from celery.task import task
from sio.workers.runner import run

@task
def sioworkers_job(env):
    """The sio-workers Celery task.

       Basically is does :func:`sio.workers.runner.run`, but
       can be used as a Celery task. See `Celery docs
       <http://celery.readthedocs.org/en/latest/getting-started/first-steps-with-celery.html>`_
       for a short tutorial on running Celery tasks.
    """
    return run(env)
