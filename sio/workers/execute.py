from __future__ import absolute_import
from sio.workers.executors import UnprotectedExecutor
import logging

logger = logging.getLogger(__name__)

def execute(command, **kwargs):
    """Wrapper for :class:`sio.workers.executors.UnprotectedExecutor` returning stdout.

       Returns tuple (return_code, stdout)
    """
    kwargs['capture_output'] = True
    with UnprotectedExecutor() as e:
        env = e(command, **kwargs)

    return env['return_code'], env['stdout']

