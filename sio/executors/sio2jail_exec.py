from sio.executors import common, interactive_common
from sio.workers.executors import Sio2JailExecutor


def run(environ):
    return common.run(environ, Sio2JailExecutor())

def interactive_run(environ):
    return interactive_common.run(environ, Sio2JailExecutor())
