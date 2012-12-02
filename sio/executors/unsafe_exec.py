from sio.executors import common
from sio.workers.executors import DetailedUnprotectedExecutor

def run(environ):
    return common.run(environ, DetailedUnprotectedExecutor(), safe_check=False)
